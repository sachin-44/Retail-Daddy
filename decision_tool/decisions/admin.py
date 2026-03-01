from django.contrib import admin
from .models import HiringDecision, HiringCriteria, Candidate, CandidateValue


class HiringCriteriaInline(admin.TabularInline):
    model = HiringCriteria
    extra = 0


class CandidateInline(admin.TabularInline):
    model = Candidate
    extra = 0


class CandidateValueInline(admin.TabularInline):
    model = CandidateValue
    extra = 0


@admin.register(HiringDecision)
class HiringDecisionAdmin(admin.ModelAdmin):
    list_display = ['role_title', 'user', 'created_at']
    list_filter  = ['created_at']
    inlines      = [HiringCriteriaInline, CandidateInline]


@admin.register(HiringCriteria)
class HiringCriteriaAdmin(admin.ModelAdmin):
    list_display = ['name', 'decision', 'weight', 'is_cost']


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ['name', 'decision']
    inlines      = [CandidateValueInline]


@admin.register(CandidateValue)
class CandidateValueAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'criteria', 'value']
