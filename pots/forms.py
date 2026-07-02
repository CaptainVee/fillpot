from django import forms

from .models import Pot

NIGERIAN_BANKS = [
    ("", "— Select bank —"),
    ("044", "Access Bank"),
    ("023", "Citibank"),
    ("063", "Access Bank (Diamond)"),
    ("050", "EcoBank"),
    ("214", "FCMB"),
    ("070", "Fidelity Bank"),
    ("011", "First Bank"),
    ("058", "GTBank"),
    ("301", "Jaiz Bank"),
    ("082", "Keystone Bank"),
    ("50211", "Kuda Bank"),
    ("999992", "OPay"),
    ("50515", "PalmPay"),
    ("076", "Polaris Bank"),
    ("101", "Providus Bank"),
    ("221", "Stanbic IBTC"),
    ("068", "Standard Chartered"),
    ("232", "Sterling Bank"),
    ("033", "UBA"),
    ("215", "Unity Bank"),
    ("035", "Wema Bank"),
    ("057", "Zenith Bank"),
]


class WithdrawalForm(forms.Form):
    bank_code = forms.ChoiceField(choices=NIGERIAN_BANKS)
    account_number = forms.CharField(max_length=10, min_length=10)
    account_name = forms.CharField(max_length=200, required=False)

    def clean_bank_code(self):
        value = self.cleaned_data["bank_code"]
        if not value:
            raise forms.ValidationError("Please select a bank.")
        return value

    def clean_account_number(self):
        value = self.cleaned_data["account_number"].strip()
        if not value.isdigit() or len(value) != 10:
            raise forms.ValidationError("Account number must be exactly 10 digits.")
        return value

    def clean_account_name(self):
        value = self.cleaned_data.get("account_name", "").strip()
        if not value:
            raise forms.ValidationError(
                "Please wait for the account name to resolve before submitting."
            )
        return value


class PotCreateForm(forms.ModelForm):
    class Meta:
        model = Pot
        fields = ("name", "description", "pot_type", "occasion_type", "target_amount", "deadline")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["target_amount"].required = False
        self.fields["deadline"].required = False
        self.fields["deadline"].input_formats = ["%Y-%m-%dT%H:%M"]
