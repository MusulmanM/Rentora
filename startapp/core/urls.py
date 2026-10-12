from django.contrib.auth import views as auth_views
from django.urls import path
from . import views
from .payments import click_callback, payme_callback

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/login/", views.StartAppLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/register/", views.register, name="register"),
    path("accounts/register/verify/", views.verify_registration, name="verify-registration"),
    path("accounts/register/resend-otp/", views.resend_registration_otp, name="resend-registration-otp"),
    path("telegram/webhook/", views.telegram_webhook, name="telegram-webhook"),
    path("profile/", views.user_profile, name="profile"),
    path("profile/phone/", views.verify_profile_phone, name="verify-profile-phone"),
    path("profile/phone/confirm/", views.confirm_profile_phone, name="confirm-profile-phone"),
    path("profile/phone/resend/", views.resend_profile_phone_otp, name="resend-profile-phone-otp"),
    path("contact/", views.contact_admin, name="contact-admin"),
    path("provider/register/", views.provider_onboarding, name="provider-onboarding"),
    path("provider/", views.provider_dashboard, name="provider-dashboard"),
    path("provider/listings/add/", views.create_listing, name="provider-create-listing"),
    path("listing/<slug:slug>/", views.listing_detail, name="listing-detail"),
    path("listing/<slug:slug>/book/", views.create_booking, name="create-booking"),
    path("my-bookings/", views.my_bookings, name="my-bookings"),
    path("my-bookings/<int:booking_id>/cancel/", views.cancel_booking, name="cancel-booking"),
    path("my-bookings/orders/<int:order_id>/pay/", views.pay_booking_order, name="pay-booking-order"),
    path("my-bookings/orders/<int:order_id>/cancel/", views.cancel_booking_order, name="cancel-booking-order"),
    path("payments/click/callback/", click_callback, name="click-payment-callback"),
    path("payments/payme/callback/", payme_callback, name="payme-payment-callback"),
    path("health/", views.health, name="health"),
    path("api/ai/rentals/", views.ai_rental_search, name="ai-rental-search"),
    path("api/listings/", views.listings_api, name="api-listings"),
    path("api/listings/<int:listing_id>/", views.listing_detail_api, name="api-listing-detail"),
    path("api/locations/districts/", views.districts_api, name="api-districts"),
    path("api/bookings/", views.bookings_api, name="api-bookings"),
    path("api/bookings/<int:booking_id>/cancel/", views.cancel_booking_api, name="api-cancel-booking"),
]
