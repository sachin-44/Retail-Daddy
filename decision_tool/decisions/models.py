from django.db import models
from django.contrib.auth.models import User


class HiringDecision(models.Model):
    """A hiring round for one role."""
    user       = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    role_title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.role_title

    class Meta:
        ordering = ['-created_at']


class HiringCriteria(models.Model):
    """
    One evaluation criteria for a role.
    weight  — raw whole number entered by user, e.g. 40
    is_cost — True means lower raw value is better (e.g. notice period in weeks)
    """
    decision    = models.ForeignKey(HiringDecision, on_delete=models.CASCADE, related_name='criteria')
    name        = models.CharField(max_length=100)
    weight      = models.PositiveIntegerField()
    is_cost     = models.BooleanField(default=False)
    description = models.CharField(max_length=255, blank=True,
                                   help_text='Optional: describe what a good value looks like')
    order       = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.name} (w={self.weight})"

    class Meta:
        ordering = ['order']


class Candidate(models.Model):
    """One candidate being evaluated."""
    decision = models.ForeignKey(HiringDecision, on_delete=models.CASCADE, related_name='candidates')
    name     = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class CandidateValue(models.Model):
    """
    The RAW value a candidate has for one criteria.
    e.g. Candidate Alice, Criteria Salary → value 55000
         Candidate Alice, Criteria Experience → value 7
         Candidate Alice, Criteria Test Score → value 82
    """
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='values')
    criteria  = models.ForeignKey(HiringCriteria, on_delete=models.CASCADE, related_name='values')
    value     = models.FloatField()

    class Meta:
        unique_together = ('candidate', 'criteria')

    def __str__(self):
        return f"{self.candidate.name} | {self.criteria.name} = {self.value}"
