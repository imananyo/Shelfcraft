from app.routers import (
    aplus,
    assets,
    brands,
    creative,
    editor,
    factory,
    jobs,
    listings,
    products,
    providers,
    system,
    videos,
)

ROUTERS = [
    system.router,
    brands.router,
    products.router,
    assets.router,
    listings.router,
    creative.router,
    editor.router,
    aplus.router,
    factory.router,
    videos.router,
    jobs.router,
    providers.router,
]
