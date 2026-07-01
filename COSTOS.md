# 💰 Costos de la infraestructura

Estimación del costo de correr el stack de `terraform-fargate/` en la región
**`us-east-2` (Ohio)**, precios **On-Demand**. Los montos son **aproximados**, en USD,
**sin impuestos ni capa gratuita (free tier)**. Para un número exacto usa la
[AWS Pricing Calculator](https://calculator.aws/).

## Costo fijo (existe aunque haya 1 sola tarea)

| Recurso                          | Cantidad | Precio unitario   | $/hora    |
|----------------------------------|:--------:|-------------------|----------:|
| Application Load Balancer (horas)| 1        | $0.0225 /hr       | $0.0225   |
| ALB · LCU (tráfico bajo demo)    | ~1 LCU   | $0.008 /LCU-hr    | ~$0.0080  |
| **NAT Gateway (horas)**          | **2**    | $0.045 /hr c/u    | **$0.0900** |
| IPv4 pública (EIP de NAT + ALB)  | ~4       | $0.005 /hr c/u    | ~$0.0200  |
| **Subtotal fijo**                |          |                   | **≈ $0.14/hr** |

> Los **2 NAT Gateways** son casi la mitad del costo fijo. Ver [Cómo abaratar](#cómo-abaratar-la-demo).

## Costo variable (según nº de tareas Fargate)

Cada tarea = **1 vCPU + 2 GB**. Fargate en `us-east-2`: **$0.04048** /vCPU-hr + **$0.004445** /GB-hr.

| Concepto                         | Por tarea | 1 tarea (reposo) | 4 tareas (máx.) |
|----------------------------------|----------:|-----------------:|----------------:|
| Fargate (1 vCPU + 2 GB)          | $0.0494   | $0.0494          | $0.1975         |
| IPv4 pública por tarea           | $0.0050   | $0.0050          | $0.0200         |
| **Subtotal Fargate**             |           | **$0.0544**      | **$0.2175**     |

## 💵 Costo total por hora

| Escenario                        | Tareas | $/hora aprox. |
|----------------------------------|:------:|--------------:|
| **En reposo** (mínimo)           | 1      | **≈ $0.19/hr** |
| **Bajo carga** (autoscaling al máximo) | 4 | **≈ $0.36/hr** |

## Extrapolación

| Periodo                                  | Reposo (1 tarea) | Máximo (4 tareas) |
|------------------------------------------|-----------------:|------------------:|
| 1 hora (demo típica)                     | ~$0.19           | ~$0.36            |
| 8 horas (un día de evento)               | ~$1.5            | ~$2.9             |
| 730 horas (1 mes continuo)               | ~$142            | ~$261             |

> **Para una demo de congreso** (levantar → mostrar → `terraform destroy`), el costo real
> es de **centavos**: 1–2 horas ≈ **$0.20 – $0.50 USD**.

## Costos variables por uso (no incluidos arriba)

Dependen del tráfico y suelen ser **céntimos** en una demo:

| Concepto                         | Precio (`us-east-2`)        |
|----------------------------------|-----------------------------|
| NAT Gateway · datos procesados   | $0.045 /GB                  |
| Transferencia de salida a Internet | ~$0.09 /GB (primeros GB)  |
| CloudWatch Logs · ingesta        | $0.50 /GB                   |
| CloudWatch Logs · almacenamiento | $0.03 /GB-mes               |
| CloudWatch alarmas (autoscaling) | $0.10 /alarma-mes           |

## Cómo abaratar la demo

- 🔴 **Destruye todo al terminar:** `terraform destroy`. Es lo que más ahorra: el stack cobra por hora aunque nadie lo use.
- 🟠 **Quita los NAT Gateways (–$0.09/hr):** son el mayor costo fijo. Como las tareas ya usan
  `assign_public_ip = true`, podrías moverlas a las **subnets públicas** y eliminar los 2 NAT
  Gateways + sus EIP. (Requiere ajustar `ecs.tf`/`network.tf`; menos "realista" pero más barato.)
- 🟡 **Reduce a 1 sola AZ** (`az_count = 1`): 1 NAT Gateway en vez de 2 (–$0.045/hr).
- 🟡 **Baja `max_capacity`** en `auto_scaling.tf` si no necesitas llegar a 4 tareas.

---

*Precios de referencia `us-east-2`, On-Demand, Linux/x86. Verifica siempre en la
[calculadora oficial de AWS](https://calculator.aws/) — los precios cambian y varían por región.*
