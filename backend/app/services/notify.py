from win11toast import toast


def send_notification(title: str, body: str) -> None:
    toast(title, body, duration="short")
