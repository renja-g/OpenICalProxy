from fastapi import FastAPI, Response, Request, HTTPException
import httpx
from ics_cleaner import modify_ics
from urllib.parse import unquote, urlparse
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from posthog import Posthog
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Initialize PostHog
posthog = Posthog(
  project_api_key=os.getenv('POSTHOG_API_KEY'),
  host=os.getenv('POSTHOG_HOST')
)


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")

ALLOWED_URL_SCHEMA = "https://www.fh-muenster.de:443/qisserver/pages/cm/exa/timetable/individualTimetableCalendarExport.faces"


def validate_url(url: str) -> bool:
    parsed_url = urlparse(url)
    return (
        parsed_url.scheme == "https"
        and parsed_url.netloc == "www.fh-muenster.de:443"
        and parsed_url.path
        == "/qisserver/pages/cm/exa/timetable/individualTimetableCalendarExport.faces"
        and "user" in parsed_url.query
        and "hash" in parsed_url.query
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Track homepage visit
    posthog.capture(
        distinct_id=str(request.client.host),
        event='homepage_visited'
    )
    home_html = Path("static/home.html").read_text()
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/{full_url:path}")
async def clean_ics(request: Request, full_url: str):
    try:
        decoded_url = unquote(full_url)
        query_params = str(request.query_params)
        complete_url = f"{decoded_url}?{query_params}" if query_params else decoded_url

        if not validate_url(complete_url):
            raise HTTPException(status_code=400, detail="Invalid URL schema")

        # Track successful calendar request
        posthog.capture(
            distinct_id=str(request.client.host),
            event='calendar_cleaned'
        )

        async with httpx.AsyncClient() as client:
            ics_response = await client.get(complete_url, timeout=10.0)
        ics_response.raise_for_status()
        cleaned_ics = modify_ics(ics_response.content)

        response = Response(content=cleaned_ics, media_type="text/calendar")
        response.headers["Content-Disposition"] = (
            "attachment; filename=CleanedCalendar.ics"
        )
        return response
    except httpx.RequestError as exc:
        # Track error
        posthog.capture(
            distinct_id=str(request.client.host),
            event='request_error',
            properties={"error_type": "RequestError", "error_message": str(exc)}
        )
        raise HTTPException(
            status_code=503, detail=f"Error fetching the iCal file: {str(exc)}"
        )
    except httpx.HTTPStatusError as exc:
        # Track error
        posthog.capture(
            distinct_id=str(request.client.host),
            event='http_error',
            properties={"status_code": exc.response.status_code}
        )
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"HTTP error: {exc.response.text}",
        )
    except Exception as exc:
        # Track error
        posthog.capture(
            distinct_id=str(request.client.host),
            event='unexpected_error',
            properties={"error_message": str(exc)}
        )
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {str(exc)}"
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )
