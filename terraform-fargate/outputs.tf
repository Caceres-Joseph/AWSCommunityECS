# outputs.tf

output "alb_hostname" {
  description = "URL pública del ALB (la app escucha en el puerto 80)"
  value       = "http://${aws_alb.main.dns_name}"
}