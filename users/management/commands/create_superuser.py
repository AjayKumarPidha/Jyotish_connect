
from django.core.management.base import BaseCommand
from users.models import User

class Command(BaseCommand):
    help = 'Create superuser for Railway'

    def handle(self, *args, **kwargs):
        if not User.objects.filter(phone='9999999999').exists():
            User.objects.create_superuser(
                phone='9999999999',
                password='Admin@1234',
            )
            self.stdout.write('Superuser created successfully!')
        else:
            self.stdout.write('Superuser already exists!')
