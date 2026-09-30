import reflex as rx

config = rx.Config(
    app_name="kbc_intent_lab",
    disable_plugins=[rx.plugins.SitemapPlugin],
    plugins=[rx.plugins.RadixThemesPlugin(theme=rx.theme(appearance="light", accent_color="cyan", radius="large"))],
)
