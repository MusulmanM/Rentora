from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from .models import Booking, BookingOrder, RentalListing
from .payments import available_payment_methods


class ListingSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    image_url = serializers.CharField(source="primary_image_url", read_only=True)
    images = serializers.SerializerMethodField()
    region_name = serializers.CharField(source="region.name_uz", read_only=True, allow_null=True)
    district_name = serializers.CharField(source="district.name_uz", read_only=True, allow_null=True)

    def get_images(self, listing):
        request = self.context.get("request")
        urls = [image.image.url for image in listing.images.all()]
        return [request.build_absolute_uri(url) for url in urls] if request else urls

    class Meta:
        model = RentalListing
        fields = [
            "id", "title", "title_ru", "title_en", "slug", "kind", "kind_label", "city", "address",
            "region", "region_name", "district", "district_name",
            "description", "description_ru", "description_en", "price_per_day", "image_url", "images", "capacity", "bedrooms", "bathrooms", "brand",
            "transmission", "year", "is_featured",
        ]


class BookingSerializer(serializers.ModelSerializer):
    listing_title = serializers.CharField(source="listing.title", read_only=True)
    listing_city = serializers.CharField(source="listing.city", read_only=True)
    listing_image = serializers.CharField(source="listing.primary_image_url", read_only=True)
    status = serializers.CharField(read_only=True)
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
        if listing.availability_status != RentalListing.AvailabilityStatus.ACTIVE:
            raise serializers.ValidationError({"listing": "Bu e'lon hozir remontda."})
        request = self.context.get("request")
        if request and listing.owner_id == request.user.pk:
            raise serializers.ValidationError({"listing": "O'zingiz joylagan e'lonni bron qila olmaysiz."})
        if check_out <= check_in:
            raise serializers.ValidationError({"check_out": "Tugash sanasi boshlanish sanasidan keyin bo'lishi kerak."})
        from django.utils import timezone
        if check_in < timezone.localdate():
            raise serializers.ValidationError({"check_in": "Bugungi kundan oldingi sana tanlanmaydi."})
        if guests < 1:
            raise serializers.ValidationError({"guests": "Kamida 1 kishi bo'lishi kerak."})
        if guests > listing.capacity:
            raise serializers.ValidationError({"guests": f"Eng ko'p sig'im: {listing.capacity}."})
        payment_method = attrs.get("payment_method", Booking.PaymentMethod.CASH)
        if payment_method not in available_payment_methods(listing):
            raise serializers.ValidationError({
                "payment_method": "Bu ijara beruvchi tanlangan to'lov turini qabul qilmaydi.",
            })
        conflicts = Booking.objects.filter(
            listing=listing,
            status__in=[
                Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.HANDED_OVER,
            ],
            check_in__lt=check_out,
            check_out__gt=check_in,
        )
        if self.instance:
            conflicts = conflicts.exclude(pk=self.instance.pk)
        if conflicts.exists():
            raise serializers.ValidationError({"check_in": "Bu e'lon tanlangan sanalarda band."})
        if BookingOrder.objects.filter(
            listing=listing,
            status__in=[BookingOrder.Status.PENDING, BookingOrder.Status.AWAITING_PAYMENT],
            check_in__lt=check_out,
            check_out__gt=check_in,
        ).exists():
            raise serializers.ValidationError({"check_in": "Bu e'lon tanlangan sanalarda boshqa buyurtma uchun band."})
        return attrs

    def create(self, validated_data):
        listing = validated_data.pop("listing")
        payment_method = validated_data.get("payment_method", Booking.PaymentMethod.CASH)
        with transaction.atomic():
            listing = RentalListing.objects.select_for_update().filter(
                pk=listing.pk,
                is_active=True,
                availability_status=RentalListing.AvailabilityStatus.ACTIVE,
            ).first()
            if listing is None:
                raise serializers.ValidationError({"listing": "Bu e'lon hozir faol emas."})
            model = Booking if payment_method == Booking.PaymentMethod.CASH else BookingOrder
            if model is BookingOrder:
                validated_data["status"] = BookingOrder.Status.AWAITING_PAYMENT
            booking = model(user=self.context["request"].user, listing=listing, **validated_data)
            try:
                booking.full_clean()
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
            booking.save()
        return booking
