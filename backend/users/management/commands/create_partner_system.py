from django.core.management.base import BaseCommand
from systems.models import PartnerSystem


class Command(BaseCommand):
    help = "Interactively create a new Partner System"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\nCreate Partner System\n"))

        name = input("System Name (required): ").strip()
        if not name:
            self.stdout.write(self.style.ERROR("System name is required. Aborting."))
            return

        if PartnerSystem.objects.filter(name=name).exists():
            self.stdout.write(
                self.style.ERROR(f"A Partner System with name '{name}' already exists.")
            )
            return

        activation_input = (
            input("Do you want to activate this system? (yes(y)/no(n)) (required): ")
            .strip()
            .lower()
        )

        if activation_input not in ["yes", "y", "no", "n"]:
            self.stdout.write(
                self.style.ERROR("Activation status is required. Aborting.")
            )
            return

        is_active = activation_input in ["yes", "y"]

        description = input("Description (optional): ").strip() or ""
        base_url = input("Base URL (optional): ").strip() or ""
        external_api_key = input("External Auth Key (optional): ").strip() or ""
        schema_url = input("Schema URL (optional): ").strip() or ""

        system = PartnerSystem.objects.create(
            name=name,
            description=description,
            base_url=base_url,
            is_active=is_active,
            external_api_key=external_api_key,
            schema_url=schema_url,
        )

        system.save()

        self.stdout.write(
            self.style.SUCCESS(f"\nPartner System '{name}' created successfully!")
        )
        self.stdout.write("\n🔑 API Key:")
        self.stdout.write(f"  • {system.api_key}\n")

        self.stdout.write(
            self.style.WARNING(
                "\nPlease note that the API key is critical. Save it securely."
            )
        )
