# Web / Android client boundary

The accepted English UX is in [design/prototype](../../design/prototype/README.md).
The working HTML/CSS/JavaScript client is packaged at
`apps/api/src/marketob_api/web/` so the API wheel and Docker image serve the exact same
assets at `/app/`, without CORS or a separate build/server. See
[Web setup](../../docs/setup/WEB.md). This directory holds locked Playwright browser
acceptance tooling; Node is not required to run the product.
Native Android packaging and the home-screen widget remain PM-019/020; SDK acceptance
and device validation were deferred by the owner. Future native packaging will reuse
the Web modules after verifying actual device integration.
