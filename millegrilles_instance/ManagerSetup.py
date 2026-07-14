from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.apps.Certificates import renew_certificates
from millegrilles_messages.messages.EnveloppeCertificat import CertificatExpire


async def setup_manager(context: InstanceContext) -> None:
    """
    Runs the initial setup.
    This method is idempotent and will not alter the system if it ready and running properly. Use it to repair
    certificates and the management apps.
    """
    await sanity_check(context)
    await generate_secrets(context)
    await setup_apps(context)


async def sanity_check(context: InstanceContext) -> None:
    # Ensure the current manager's signing certificate is valid and not expired.
    try:
        context.reload()
    except CertificatExpire:
        raise Exception("The Manager key is expired - renew using the CA signing key refresh script (you need the MilleGrille CA key for this)")
    except FileNotFoundError:
        raise Exception("The Manager key is missing - you may have to reinstall the system.")


async def generate_secrets(context: InstanceContext):
    # Generate missing/expired secrets
    renew_certificates(context)


async def setup_apps(context: InstanceContext):
    pass
