"""Admin-only endpoints for signature image uploads.

Lets the disclaimer change form drop a new image into the picker without
having to leave the page. The endpoint creates a ``SignatureImage`` row
with a slug derived from the filename (or supplied explicitly) and
returns enough info for the picker to insert ``{image["slug"]}`` into
the editor.
"""

from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views.generic import View

from ..models import SignatureImage


@method_decorator(staff_member_required, name="dispatch")
class SignatureImageQuickUploadView(View):
    """Create a SignatureImage from a multipart/form-data POST.

    Accepts:
        image       — the uploaded file (required)
        slug        — optional; derived from the filename if absent
        name        — optional; derived from the filename if absent
        alt_text    — optional

    Returns 201 with ``{slug, name, url, alt_text}`` on success, 400 on
    validation error.
    """

    def post(self, request: HttpRequest) -> JsonResponse:
        upload = request.FILES.get("image")
        if upload is None:
            return JsonResponse({"error": "Missing 'image' file."}, status=400)

        raw_slug = request.POST.get("slug", "").strip()
        raw_name = request.POST.get("name", "").strip()
        alt_text = request.POST.get("alt_text", "").strip()

        # Derive slug + name from the filename if the caller didn't
        # bother. ``slugify`` is good enough — we collision-check below.
        stem = upload.name.rsplit(".", 1)[0]
        slug = slugify(raw_slug or stem)[:64] or "image"
        name = raw_name or stem

        if not slug:
            return JsonResponse({"error": "Could not derive a slug."}, status=400)

        # Auto-suffix on collision so re-uploading "logo.png" twice
        # doesn't blow up — the user can rename in the admin later.
        unique_slug = slug
        counter = 2
        while SignatureImage.objects.filter(slug=unique_slug).exists():
            unique_slug = f"{slug}-{counter}"
            counter += 1
            if counter > 1000:  # pathological safety net
                return JsonResponse(
                    {"error": "Could not find a free slug."}, status=400
                )

        image = SignatureImage.objects.create(
            slug=unique_slug,
            name=name,
            alt_text=alt_text,
            image=upload,
        )
        return JsonResponse(
            {
                "slug": image.slug,
                "name": image.name,
                "alt_text": image.alt_text,
                "url": image.image.url,
            },
            status=201,
        )
