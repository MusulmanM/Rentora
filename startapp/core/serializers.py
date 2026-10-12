from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from .models import Booking, RentalListing, home, car


class homeSerializer(serializers.ModelSerializer):
    class Meta:
        model = home
        fields = ["id", "name", "address", "price", "description", "created_at"]


class carSerializer(serializers.ModelSerializer):
    class Meta:
        model = car
        fields = ["id", "name", "brand", "year", "price", "description", "created_at"]


class ListingSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = RentalListing
        fields = [
            "id", "title", "title_ru", "title_en", "slug", "kind", "kind_label", "city", "address",
            "description", "description_ru", "description_en", "price_per_day", "image_url", "capacity", "bedrooms", "bathrooms", "brand",
            "transmission", "year", "is_featured",
        ]


class BookingSerializer(serializers.ModelSerializer):
    listing_title = serializers.CharField(source="listing.title", read_only=True)
    listing_city = serializers.CharField(source="listing.city", read_only=True)
    listing_image = serializers.CharField(source="listing.image_url", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payment_method_label = serializers.CharField(source="get_payment_method_display", read_only=True)
    days = serializers.IntegerField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id", "listing", "listing_title", "listing_city", "listing_image", "check_in", "check_out",
            "guests", "payment_method", "payment_method_label", "days", "total_price", "status", "status_label", "created_at",
        ]
        read_only_fields = ["id", "total_price", "status", "created_at"]

    def validate(self, attrs):
        listing = attrs.get("listing", getattr(self.instance, "listing", None))
        check_in = attrs.get("check_in", getattr(self.instance, "check_in", None))
        check_out = attrs.get("check_out", getattr(self.instance, "check_out", None))
        guests = attrs.get("guests", getattr(self.instance, "guests", 1))
        if not listing or not check_in or not check_out:
            return attrs
        if not listing.is_active:
            raise serializers.ValidationError({"listing": "Bu e'lon hozir faol emas."})
        if check_out <= check_in:
            raise serializers.ValidationError({"check_out": "Tugash sanasi boshlanish sanasidan keyin bo'lishi kerak."})
        from django.utils import timezone
        if check_in < timezone.localdate():
            raise serializers.ValidationError({"check_in": "Bugungi kundan oldingi sana tanlanmaydi."})
        if guests < 1:
            raise serializers.ValidationError({"guests": "Kamida 1 kishi bo'lishi kerak."})
        if guests > listing.capacity:
            raise serializers.ValidationError({"guests": f"Eng ko'p sig'im: {listing.capacity}."})
        conflicts = Booking.objects.filter(
            listing=listing,
            status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
            check_in__lt=check_out,
            check_out__gt=check_in,
        )
        if self.instance:
            conflicts = conflicts.exclude(pk=self.instance.pk)
        if conflicts.exists():
            raise serializers.ValidationError({"check_in": "Bu e'lon tanlangan sanalarda band."})
        return attrs

    def create(self, validated_data):
        listing = validated_data.pop("listing")
        with transaction.atomic():
            listing = RentalListing.objects.select_for_update().filter(pk=listing.pk, is_active=True).first()
            if listing is None:
                raise serializers.ValidationError({"listing": "Bu e'lon hozir faol emas."})
            booking = Booking(user=self.context["request"].user, listing=listing, **validated_data)
            try:
                booking.full_clean()
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
            booking.save()
        return booking
