from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from contributions.models import Contributor

from .forms import LoginForm, SignupForm


def signup(request):
    if request.user.is_authenticated:
        return redirect("pots:dashboard")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Claim any guest contributions made with this email before signing up
            Contributor.objects.filter(email=user.email, user=None).update(user=user)
            login(request, user)
            messages.success(request, "Welcome to FillPot!")
            return redirect("pots:dashboard")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})


class FillPotLoginView(LoginView):
    form_class = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


def logout_view(request):
    logout(request)
    return redirect("accounts:login")
