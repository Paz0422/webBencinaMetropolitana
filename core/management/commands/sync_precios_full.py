from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = "Ejecuta sync_precios para una matriz de regiones y combustibles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--regiones",
            type=int,
            nargs="+",
            default=[13],
            help="Lista de regiones (ej: --regiones 13 5).",
        )
        parser.add_argument(
            "--combustibles",
            type=int,
            nargs="+",
            default=[1, 2, 3, 4],
            help="Lista de combustibles (ej: --combustibles 1 2 3 4).",
        )

    def handle(self, *args, **options):
        regiones = options["regiones"]
        combustibles = options["combustibles"]
        total = len(regiones) * len(combustibles)
        corrida = 0

        self.stdout.write(
            self.style.NOTICE(
                f"Iniciando sync_precios_full con {len(regiones)} regiones y "
                f"{len(combustibles)} combustibles ({total} combinaciones)."
            )
        )

        for region_id in regiones:
            for combustible_id in combustibles:
                corrida += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"[{corrida}/{total}] region={region_id} combustible={combustible_id}"
                    )
                )
                call_command(
                    "sync_precios",
                    region=region_id,
                    combustible=combustible_id,
                )

        self.stdout.write(self.style.SUCCESS("sync_precios_full finalizado"))
