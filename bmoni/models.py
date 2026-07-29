from django.db import models


class BmoniApiLog(models.Model):
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10, default='POST')
    request_body = models.JSONField(blank=True, null=True)
    response_body = models.JSONField(blank=True, null=True)
    status_code = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    duration_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "BMONI API Call Log"
        verbose_name_plural = "BMONI API Call Logs"

    def __str__(self):
        return f"{self.method} {self.endpoint} - {self.status_code}"