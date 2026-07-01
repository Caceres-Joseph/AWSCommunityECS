# Terraform · AWS ECS Fargate

Despliega una app web en **AWS ECS Fargate**, detrás de un
**Application Load Balancer**, con VPC propia, autoscaling y logs en CloudWatch.

## Arquitectura

- **VPC** `172.17.0.0/16` con 2 subnets públicas + 2 privadas (2 AZs)
- **Internet Gateway** + **2 NAT Gateways** (uno por AZ) para salida de las tareas privadas
- **ALB** público (puerto 80) → **ECS Service** Fargate en subnets privadas
- **Task**: 1 vCPU / 2 GB, imagen desde ECR (`app:latest`)
- **Autoscaling** por CPU (alarmas CloudWatch) + **CloudWatch Logs** (`/ecs/cb-app`)

![Diagrama](../aws.png)

## Requisitos

- [Terraform](https://www.terraform.io/downloads.html) ≥ 1.13 (probado con 1.15.3)
- AWS CLI v2
- Credenciales de AWS con permisos suficientes (aquí se usan credenciales temporales SSO/STS)

## Cómo desplegar

1. **Exporta las credenciales** de AWS en la terminal (ejemplo con credenciales temporales STS):

    ```bash
    export AWS_ACCESS_KEY_ID="..."
    export AWS_SECRET_ACCESS_KEY="..."
    export AWS_SESSION_TOKEN="..."      # solo si son credenciales temporales
    ```

    Verifica que la sesión es correcta:

    ```bash
    aws sts get-caller-identity
    ```

2. **Inicializa** Terraform (descarga el provider de AWS):

    ```bash
    cd terraform-fargate
    terraform init
    ```

3. **Revisa el plan**:

    ```bash
    terraform plan
    ```

4. **Aplica**:

    ```bash
    terraform apply
    ```

    Al terminar, Terraform imprime la URL pública:

    ```
    alb_hostname = "http://cb-load-balancer-XXXX.us-east-2.elb.amazonaws.com"
    ```

    Ábrela en el navegador para ver la página **"Hola Universidad"**. Las tareas ECS
    pueden tardar 1–2 min en pasar el health check del ALB.

## ⚠️ Costos — destruir después de la demo

Este stack levanta recursos **facturables mientras estén arriba**: 2 NAT Gateways, ALB y
varias tareas Fargate. Cuando termines la demo, **destruye todo** para no seguir pagando:

```bash
terraform destroy
```

## Variables útiles (`variable.tf`)

| Variable         | Default                          | Descripción                         |
|------------------|----------------------------------|-------------------------------------|
| `aws_region`     | `us-east-2`                      | Región de despliegue                |
| `app_image`      | `...ecr.../app:latest`           | Imagen del contenedor (ECR)         |
| `app_port`       | `80`                             | Puerto de la app / ALB / target     |
| `app_count`      | `1`                              | Tareas deseadas iniciales           |
| `fargate_cpu`    | `1024` (1 vCPU)                  | CPU de la tarea                     |
| `fargate_memory` | `2048` MiB                       | Memoria de la tarea                 |

> **Nota autoscaling:** `auto_scaling.tf` fija `min_capacity = 3`, así que aunque
> `app_count = 1`, el servicio escalará a un **mínimo de 3 tareas**. Para una demo más
> barata puedes bajar `min_capacity` a `1`.

## CI/CD

`.github/workflows/deploy.yml` construye la imagen desde `app/`, la sube a ECR y actualiza
el servicio ECS en cada push a `main` (requiere los secrets `AWS_ACCESS_KEY_ID` y
`AWS_SECRET_ACCESS_KEY` en el repo).
