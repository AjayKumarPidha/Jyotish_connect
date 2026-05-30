from rest_framework import serializers
from .models import AstrologerProfile, Review, Category, Specialty, Language


class CategorySerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    
    class Meta:
        model  = Category
        fields = ['id', 'name', 'image']
        
    def get_image(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        if request:
            # request.build_absolute_uri respects the actual port
            return request.build_absolute_uri(obj.image.url)
        # fallback: read MEDIA_URL from settings
        from django.conf import settings
        return f"{settings.MEDIA_URL}{obj.image}"



class SpecialtySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Specialty
        fields = ['id', 'name', 'description']


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Language
        fields = ['id', 'name']


class ReviewSerializer(serializers.ModelSerializer):
    client_phone = serializers.CharField(source='client.phone', read_only=True)

    class Meta:
        model  = Review
        fields = ['id', 'client_phone', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value


class AstrologerListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing astrologers."""
    categories  = CategorySerializer(many=True, read_only=True)
    profile_photo = serializers.SerializerMethodField()

    class Meta:
        model  = AstrologerProfile
        fields = [
            'id', 'display_name', 'bio', 'experience_years',
            'categories', 'specialties', 'languages',
            'chat_rate_per_min', 'call_rate_per_min', 'video_rate_per_min',
            'status', 'average_rating', 'total_sessions', 'profile_photo',
        ]
        
    def get_profile_photo(self, obj):
        if not obj.profile_photo:
            return None
        request = self.context.get('request')
        if request:
            # request.build_absolute_uri respects the actual port
            return request.build_absolute_uri(obj.profile_photo.url)
        # fallback: read MEDIA_URL from settings
        from django.conf import settings
        return f"{settings.MEDIA_URL}{obj.profile_photo}"

class AstrologerDetailSerializer(serializers.ModelSerializer):
    categories   = CategorySerializer(many=True, read_only=True)

    reviews      = ReviewSerializer(many=True, read_only=True)
    profile_photo = serializers.SerializerMethodField()   # ← manual URL build

    class Meta:
        model  = AstrologerProfile
        fields = [
            'id', 'display_name', 'bio', 'experience_years',
            'categories', 'specialties', 'languages',
            'chat_rate_per_min', 'call_rate_per_min', 'video_rate_per_min',
            'status', 'average_rating', 'total_sessions',
            'profile_photo', 'reviews',
        ]

    def get_profile_photo(self, obj):
        if not obj.profile_photo:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.profile_photo.url)
        from django.conf import settings
        return f"{settings.MEDIA_URL}{obj.profile_photo}"
    
class AstrologerDetailSerializer(AstrologerListSerializer):
    """Full serializer for astrologer detail view including reviews."""
    reviews = ReviewSerializer(many=True, read_only=True)

    class Meta(AstrologerListSerializer.Meta):
        fields = AstrologerListSerializer.Meta.fields + ['reviews']


class AstrologerStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AstrologerProfile
        fields = ['status']
