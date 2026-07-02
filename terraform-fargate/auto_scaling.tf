# auto_scaling.tf
#
# Escalado horizontal por CPU con STEP SCALING.
# A diferencia del target tracking, aquí controlamos nosotros las alarmas de
# CloudWatch (periodo y datapoints), para que la demo reaccione en ~2 minutos
# en vez de esperar 3 min para subir y 15 min para bajar.
#
# Límite físico: la métrica CPUUtilization de ECS se publica cada 1 minuto, así
# que la detección no puede ser más rápida de ~1-2 min.

resource "aws_appautoscaling_target" "target" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.main.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  role_arn           = aws_iam_role.ecs_auto_scale_role.arn
  min_capacity       = 1
  max_capacity       = 4
}

# --- Scale OUT: +2 tareas cuando CPU >= 50% durante ~2 min ---
resource "aws_appautoscaling_policy" "up" {
  name               = "cb-scale-up"
  service_namespace  = "ecs"
  resource_id        = aws_appautoscaling_target.target.resource_id
  scalable_dimension = "ecs:service:DesiredCount"
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 30
    metric_aggregation_type = "Average"

    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 2 # salto grande = más visible en la demo
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "cb-cpu-high"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  statistic           = "Average"
  period              = 60 # 1 datapoint por minuto
  evaluation_periods  = 2  # 2 datapoints -> ~2 min (pon 1 para ~1 min)
  threshold           = 40 # la CPU por tarea topa en ~50%; 40 da margen para disparar

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.main.name
  }

  alarm_actions = [aws_appautoscaling_policy.up.arn]
}

# --- Scale IN: -1 tarea cuando CPU <= 20% durante ~2 min ---
resource "aws_appautoscaling_policy" "down" {
  name               = "cb-scale-down"
  service_namespace  = "ecs"
  resource_id        = aws_appautoscaling_target.target.resource_id
  scalable_dimension = "ecs:service:DesiredCount"
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 60
    metric_aggregation_type = "Average"

    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = -1
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "cpu_low" {
  alarm_name          = "cb-cpu-low"
  comparison_operator = "LessThanOrEqualToThreshold"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 2 # scale-in en ~2 min en vez de 15
  threshold           = 20

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.main.name
  }

  alarm_actions = [aws_appautoscaling_policy.down.arn]
}
