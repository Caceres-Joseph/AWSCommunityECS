# App de demo — Generador de carga de CPU

Pequeña app **Flask** contenerizada que se usa para demostrar el **escalado horizontal**
de ECS Fargate en vivo. Expone endpoints para **subir y bajar la CPU** de cada tarea bajo
demanda (p. ej. desde Postman) y reporta el **% de CPU y RAM** reales del contenedor.

Corre en el puerto **80** (igual que el ALB, el target group y los security groups).

## Endpoints

| Método | Ruta       | Descripción                                                                 |
|--------|------------|-----------------------------------------------------------------------------|
| `GET`  | `/`        | Página HTML (auto-refresh cada 3s): tarea que respondió, estado, CPU y RAM  |
| `GET`  | `/health`  | Health check del ALB (JSON `status: ok` + estado)                           |
| `GET`  | `/status`  | Estado en JSON (ver campos abajo)                                           |
| `POST` | `/burn`    | **Sube** la CPU de la tarea que reciba el request (auto-expira)             |
| `POST` | `/stop`    | **Baja** la CPU de la tarea que reciba el request                          |

### `POST /burn` — cuerpo (JSON, opcional)

```json
{ "seconds": 120, "workers": 1, "load": 0.85 }
```

- `seconds`: duración de la carga antes de apagarse sola (default 120).
- `workers`: procesos que queman CPU en paralelo (default 1).
- `load`: fracción de un núcleo por worker, 0–1 (default `0.85` ≈ 85%). Se deja headroom
  a propósito para que el health check del ALB no falle bajo carga.

### Campos de `/status`

```json
{
  "task": "0316a10a4024",   // hostname del contenedor = identifica la tarea ECS
  "burning": true,           // ¿está quemando CPU?
  "workers": 1,
  "seconds_left": 13,        // segundos hasta que la carga se apaga sola
  "cpu_percent": 83.3,       // % de CPU relativo a la vCPU asignada (== métrica de CloudWatch)
  "mem_used_mb": 42.6,
  "mem_limit_mb": 512.0,
  "mem_percent": 8.3
}
```

> El `cpu_percent` y la RAM se leen de los **cgroups** del contenedor (v2 y v1), por lo que
> el porcentaje es relativo a la vCPU asignada — el mismo criterio que usa la métrica
> `ECSServiceAverageCPUUtilization` que dispara el autoscaling.

## Probar localmente

```bash
# build
docker build -t demo-escalado .

# correr limitando recursos como en Fargate (1 vCPU / 512 MB)
docker run --rm --cpus=1 --memory=512m -p 8080:80 demo-escalado
```

En otra terminal:

```bash
curl -s localhost:8080/status
curl -s -XPOST localhost:8080/burn -H 'Content-Type: application/json' \
  -d '{"seconds":20,"workers":1,"load":0.85}'
sleep 6 && curl -s localhost:8080/status      # cpu_percent ~83%
docker stats --no-stream demo-escalado         # debe coincidir con cpu_percent
```

O abre <http://localhost:8080> para ver la página con CPU/RAM en vivo.

## Publicar en ECR (para desplegar en ECS)

```bash
# 1. Autenticar Docker contra el registro ECR
aws ecr get-login-password --region us-east-2 | \
  docker login --username AWS --password-stdin 637423235030.dkr.ecr.us-east-2.amazonaws.com

# 2. Build (amd64: el Dockerfile ya fija --platform=linux/amd64)
docker build -t 637423235030.dkr.ecr.us-east-2.amazonaws.com/app:latest .

# 3. Push
docker push 637423235030.dkr.ecr.us-east-2.amazonaws.com/app:latest
```

Luego despliega la infraestructura desde [`../terraform-fargate`](../terraform-fargate/Readme.md)
con `terraform apply`.

## Uso en la demo de escalado

1. Despliega la infra y abre la URL `alb_hostname` que imprime Terraform.
2. En **Postman** (colección [`../demo-escalado.postman_collection.json`](../demo-escalado.postman_collection.json)),
   pon la URL del ALB en la variable `alb_url`.
3. Abre el **Collection Runner** con el request *"Subir CPU (burn)"*, ~30 iteraciones y
   delay de 2000 ms → **Run**. El round-robin del ALB reparte el burn a todas las tareas.
4. Observa el escalado (consola ECS o `watch` — ver README de `terraform-fargate`): sube de
   1 hasta 4 tareas. Al detener el Runner, el burn auto-expira y ECS reduce las tareas.

## Archivos

- `app.py` — la aplicación Flask.
- `requirements.txt` — dependencias (`flask`).
- `Dockerfile` — imagen basada en `python:3.12-slim`, expone el puerto 80.
