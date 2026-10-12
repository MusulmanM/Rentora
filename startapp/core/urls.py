from django.contrib.auth import views as auth_views
from django.urls import path
from . import views
from .payments import click_callback, payme_callback

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/login/", views.StartAppLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/register/", views.register, name="register"),
    path("listing/<slug:slug>/", views.listing_detail, name="listing-detail"),
    path("listing/<slug:slug>/book/", views.create_booking, name="create-booking"),
    path("my-bookings/", views.my_bookings, name="my-bookings"),
    path("my-bookings/<int:booking_id>/cancel/", views.cancel_booking, name="cancel-booking"),
    path("my-bookings/orders/<int:order_id>/pay/", views.pay_booking_order, name="pay-booking-order"),
    path("my-bookings/orders/<int:order_id>/cancel/", views.cancel_booking_order, name="cancel-booking-order"),
    path("payments/click/callback/", click_callback, name="click-payment-callback"),
    path("payments/payme/callback/", payme_callback, name="payme-payment-callback"),
    path("health/", views.health, name="health"),
    path("api/listings/", views.listings_api, name="api-listings"),
    path("api/listings/<int:listing_id>/", views.listing_detail_api, name="api-listing-detail"),
    path("api/bookings/", views.bookings_api, name="api-bookings"),
    path("api/bookings/<int:booking_id>/cancel/", views.cancel_booking_api, name="api-cancel-booking"),
]
