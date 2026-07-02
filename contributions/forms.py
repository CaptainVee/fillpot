from django import forms

from .models import Contributor


class ContributorJoinForm(forms.Form):
    full_name = forms.CharField(max_length=200, label="Your full name")
    email = forms.EmailField(label="Your email")
    amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=1,
        label="Amount (₦)",
    )
    is_anonymous = forms.BooleanField(
        required=False,
        label="Show as Anonymous on the public feed",
    )
    wants_group_notifications = forms.BooleanField(
        required=False,
        label="Notify me every time someone contributes",
    )

    def __init__(self, *args, pot=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pot = pot
        if pot and pot.pot_type == "pledge":
            self.fields["amount"].label = "Total pledge amount (₦)"
            self.fields["amount"].help_text = "You'll pay this in installments at your own pace."
        else:
            self.fields["amount"].label = "How much will you contribute? (₦)"

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email", "").lower()
        if self.pot and email:
            if Contributor.objects.filter(pot=self.pot, email=email).exists():
                # Signal to the view that this person already joined
                self.already_joined = True
            else:
                self.already_joined = False
            cleaned["email"] = email
        return cleaned
