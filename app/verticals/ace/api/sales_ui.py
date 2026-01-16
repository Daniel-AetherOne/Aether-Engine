from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["sales-ui"])
templates = Jinja2Templates(directory="app/verticals/ace/templates")


@router.get("/sales/quote", response_class=HTMLResponse)
def sales_quote_page(request: Request):
    return templates.TemplateResponse("sales_quote.html", {"request": request})
