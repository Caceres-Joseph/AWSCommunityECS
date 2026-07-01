# auto_scaling.tf
#
# Escalado horizontal por CPU (target tracking).
# Para la demo: la app expone POST /burn que sube la CPU de la tarea.
# Cuando el CPU promedio del servicio supera `target_value`, ECS agrega tareas
# hasta `max_capacity`; al bajar la carga, las quita hasta `min_capacity`.

resource "aws_appautoscaling_target" "target" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.main.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  role_arn           = aws_iam_role.ecs_auto_scale_role.arn
  min_capacity       = 1
  max_capacity       = 4
}

# Mantiene el CPU promedio del servicio cerca del 50%.
# Escala hacia afuera rápido (30s) y hacia adentro más lento (60s) para que
# en la demo se note el "scale out" y luego el "scale in".
resource "aws_appautoscaling_policy" "cpu" {
  name               = "cb-cpu-target-tracking"
  service_namespace  = "ecs"
  resource_id        = aws_appautoscaling_target.target.resource_id
  scalable_dimension = "ecs:service:DesiredCount"
  policy_type        = "TargetTrackingScaling"

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    target_value       = 50
    scale_out_cooldown = 30
    scale_in_cooldown  = 60
  }

  depends_on = [aws_appautoscaling_target.target]
}
