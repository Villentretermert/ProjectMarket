"""Flet Web/Android feasibility screen. All data and actions are explicitly demo."""

import os

import flet as ft
from demo_model import CHANNELS, NEWS, PRODUCT, VIEWS, channel_from_route, decode_preferences, encode_preferences

PREFERENCES_KEY = "marketob.pm002.preferences.v1"


def content_card(*controls: ft.Control) -> ft.Card:
    return ft.Card(content=ft.Container(content=ft.Column(list(controls), spacing=12), padding=20), elevation=0, variant=ft.CardVariant.OUTLINED)


def view_series(mode: str) -> ft.Control:
    if mode == "values":
        return ft.Column([ft.Text(f"Day {i + 1}: {value} views") for i, value in enumerate(VIEWS)])
    # A small labeled bar chart avoids an extra binary package in the feasibility build.
    return ft.Column([
        ft.Text("Catalog views · sample series", weight=ft.FontWeight.BOLD),
        ft.Row([
            ft.Column([
                ft.Text(str(value), size=12),
                ft.Container(height=100 * value / max(VIEWS), width=20, bgcolor=ft.Colors.BLUE_600, border_radius=4),
                ft.Text(str(i + 1), size=12),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.END)
            for i, value in enumerate(VIEWS)
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.END),
        ft.Text("Day 1–7 · Views", size=12),
    ])


async def main(page: ft.Page):
    page.title = "MarkeTOB · feasibility preview"
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE, use_material3=True)
    page.padding = 16
    page.scroll = ft.ScrollMode.AUTO
    preferences = ft.SharedPreferences()
    favorites: set[str] = set()
    chart_view = "bars"
    status = ft.Text("Local demo fixtures · no backend connected", selectable=True)
    profile = ft.Text("Previewing as Visitor", selectable=True)
    body = ft.Column(spacing=12)

    async def save(_=None):
        try:
            await preferences.set(PREFERENCES_KEY, encode_preferences(favorites, chart_view))
        except Exception:
            status.value = "Preferences could not be saved. This session remains usable."
        page.update()

    async def toggle_favorite(event):
        selected = channel_from_route(page.route)
        if selected not in CHANNELS:
            return
        if selected in favorites:
            favorites.remove(selected)
        else:
            favorites.add(selected)
        render()
        await save()

    async def toggle_chart(event):
        nonlocal chart_view
        chart_view = "values" if chart_view == "bars" else "bars"
        render()
        await save()

    def request_demo(event):
        status.value = "Demo request: Pending. No order was submitted and no payment was taken."
        page.update()

    def local_profile(event):
        profile.value = "Previewing as Bob · local demo profile"
        status.value = "Demo profile selected. Real local accounts and access checks are planned in PM-006."
        page.update()

    def render(_=None):
        selected = channel_from_route(page.route)
        controls: list[ft.Control] = []
        if selected is None:
            controls = [ft.Text("Channels", size=24, weight=ft.FontWeight.BOLD)]
            for key, value in CHANNELS.items():
                controls.append(content_card(
                    ft.Text(value["title"], size=20), ft.Text(value["description"]),
                    ft.Button("Open channel", on_click=lambda e, key=key: page.navigate("/channels/" + key)),
                    ft.Text("Saved" if key in favorites else "Not saved", size=12),
                ))
        elif selected == "missing":
            controls = [content_card(ft.Text("Channel unavailable", size=22), ft.Text("The preview does not contain this channel."))]
        else:
            controls = [ft.Row([
                ft.Text(CHANNELS[selected]["title"], size=24, weight=ft.FontWeight.BOLD),
                ft.Button("Saved" if selected in favorites else "Save channel", on_click=toggle_favorite),
            ], wrap=True), ft.Text("Public channel · sample data · source time is illustrative", size=12)]
            if selected == "shop":
                controls.append(content_card(ft.Text(PRODUCT["title"], size=20), ft.Text(PRODUCT["description"]), ft.Text("EUR 18.00", size=24), ft.Text("In stock · Demo item"), ft.Button("Send request", on_click=request_demo)))
                controls.append(content_card(view_series(chart_view), ft.Button("Show values" if chart_view == "bars" else "Show chart", on_click=toggle_chart)))
            else:
                for item in NEWS:
                    controls.append(content_card(ft.Text(item["title"], size=20), ft.Text(item["body"])))
                controls.append(content_card(ft.Text("Home screen widget", size=18), ft.Text("Native widget integration is a separate PM-002 check; this card is not an Android widget.")))
        body.controls = controls
        page.update()

    page.on_route_change = render
    page.add(
        ft.Row([ft.Text("MarkeTOB", size=28, weight=ft.FontWeight.BOLD), ft.Text("PM-002 · DEMO", size=12)], wrap=True),
        ft.Row([ft.Button("Channels", on_click=lambda e: page.navigate("/")), ft.Button("Use local demo profile", on_click=local_profile)], wrap=True),
        profile,
        ft.Divider(), body, ft.Divider(), status,
    )
    render()
    try:
        favorites, chart_view = decode_preferences(await preferences.get(PREFERENCES_KEY))
        render()
    except Exception:
        status.value = "Preference storage unavailable; using demo defaults."
        page.update()


if __name__ == "__main__":
    if os.environ.get("MARKETOB_PREVIEW_WEB") == "1":
        # view=None alone selects Flet's native socket transport, not HTTP.
        os.environ["FLET_FORCE_WEB_SERVER"] = "true"
        os.environ["FLET_WEB_NO_CDN"] = "true"
        ft.run(main, view=None, host="127.0.0.1", port=8551)
    else:
        ft.run(main)
