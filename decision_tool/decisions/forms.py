from django import forms
from django.forms import formset_factory


class RoleTitleForm(forms.Form):
    role_title = forms.CharField(
        max_length=255,
        label="What role are you hiring for?",
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'e.g. Senior Backend Developer'
        })
    )


class CriteriaForm(forms.Form):
    """
    One criteria row.
    weight     — any whole number, system normalizes automatically
    is_cost    — tick if lower value is better (e.g. salary, notice period)
    scale_min  — optional realistic floor for this criteria in the market
    scale_max  — optional realistic ceiling for this criteria in the market

    If scale_min/scale_max are provided, normalization uses those bounds
    instead of deriving bounds from the candidates in this session.
    This prevents a tiny gap between candidates from dominating the score.
    """
    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. Salary, Experience, Test Score'
        })
    )
    weight = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 40',
            'min': '1',
        })
    )
    is_cost = forms.BooleanField(
        required=False,
        label="Lower is better",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    description = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. Annual salary in GBP (optional)'
        })
    )
    scale_min = forms.FloatField(
        required=False,
        label='Realistic min',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 0',
            'step': 'any',
        })
    )
    scale_max = forms.FloatField(
        required=False,
        label='Realistic max',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 100',
            'step': 'any',
        })
    )


CriteriaFormSet = formset_factory(CriteriaForm, extra=0, min_num=2, validate_min=True)


class CandidateNameForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. Alice Johnson'
        })
    )


CandidateNameFormSet = formset_factory(CandidateNameForm, extra=0, min_num=2, validate_min=True)


class CandidateValueForm(forms.Form):
    """
    One form per candidate.
    Dynamically adds one FloatField per criteria.
    User enters the RAW actual value — salary=55000, experience=7, test score=82.
    Normalization happens in scoring.py, not here.
    """
    def __init__(self, *args, criteria_list=None, candidate_name='', **kwargs):
        super().__init__(*args, **kwargs)
        self.candidate_name = candidate_name
        if criteria_list:
            for c in criteria_list:
                hint = f" ({c['description']})" if c.get('description') else ''
                self.fields[f'c_{c["id"]}'] = forms.FloatField(
                    label=f"{c['name']}{hint}",
                    widget=forms.NumberInput(attrs={
                        'class': 'form-control',
                        'placeholder': f"Enter {c['name'].lower()} value",
                        'step': 'any',
                        'style': 'font-size:1rem; padding: 0.5rem 0.75rem;',
                    })
                )

    def get_values(self, criteria_list):
        """
        Return {criteria_id: raw_value} from cleaned_data.
        Keys are stored as integers so scoring engine lookups work correctly.
        Note: Django session JSON will convert these to strings on reload,
        which is why scoring.py uses _get_val() to handle both.
        """
        return {
            int(c['id']): self.cleaned_data[f'c_{c["id"]}']
            for c in criteria_list
            if f'c_{c["id"]}' in self.cleaned_data
        }
