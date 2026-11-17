from app import auth, public_api
from app.routers import (
    aplus,
    assets,
    brands,
    competitors,
    creative,
    editor,
    factory,
    growth,
    integrations,
    jobs,
    listings,
    products,
    providers,
    reviews,
    share,
    system,
    videos,
)

ROUTERS = [
    system.router,
    auth.router,
    brands.router,
    integrations.router,  # before products: /products/import-text must not be captured by /products/{id}
    competitors.router,
    reviews.router,  # before products: /products/{id}/reviews/... are more specific
    products.router,
    assets.router,
    growth.router,  # before listings/videos: /listings/bulk and /videos/spin are static paths
    listings.router,
    creative.router,
    editor.router,
    aplus.router,
    factory.router,
    videos.router,
    jobs.router,
    providers.router,
    share.router,
    public_api.manage,
]
