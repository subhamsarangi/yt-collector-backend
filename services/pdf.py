try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False


def _require_weasyprint():
    if not WEASYPRINT_AVAILABLE:
        raise RuntimeError(
            "WeasyPrint is not available on this platform. PDF generation only works on the OCI server."
        )


def render_video_pdf(video: dict) -> bytes:
    _require_weasyprint()
    transcript_lines = (
        video.get("transcript") or "No transcript available."
    ).splitlines()
    transcript_html = "".join(
        f"<p>{line}</p>" for line in transcript_lines if line.strip()
    )

    channel = video.get("channels") or {}
    channel_name = channel.get("name") if isinstance(channel, dict) else None
    channel_url = channel.get("url") if isinstance(channel, dict) else None
    channel_html = ""
    if channel_name:
        if channel_url:
            channel_html = f'<p><strong>Channel:</strong> <a href="{channel_url}">{channel_name}</a></p>'
        else:
            channel_html = f"<p><strong>Channel:</strong> {channel_name}</p>"

    html = f"""
    <html><body style="font-family: sans-serif; padding: 2rem;">
      <img src="{video.get('thumbnail_r2_url', '')}" style="max-width:100%;"><br>
      <h1>{video.get('title', '')}</h1>
      {channel_html}
      <p><strong>Published:</strong> {video.get('published_at', '')}</p>
      <p><strong>Views:</strong> {video.get('metadata', {}).get('view_count', 'N/A')} &nbsp;
         <strong>Likes:</strong> {video.get('metadata', {}).get('like_count', 'N/A')}</p>
      <hr>
      <h2>Transcript</h2>
      {transcript_html}
    </body></html>
    """
    return HTML(string=html).write_pdf()


def render_topic_pdf(topic: dict, videos: list[dict]) -> bytes:
    _require_weasyprint()
    sections = ""
    for v in videos:
        transcript_lines = (v.get("transcript") or "").splitlines()
        transcript_html = "".join(
            f"<p>{line}</p>" for line in transcript_lines if line.strip()
        )
        channel = v.get("channels") or {}
        channel_name = channel.get("name") if isinstance(channel, dict) else None
        channel_url = channel.get("url") if isinstance(channel, dict) else None
        channel_html = ""
        if channel_name:
            if channel_url:
                channel_html = f'<p><strong>Channel:</strong> <a href="{channel_url}">{channel_name}</a></p>'
            else:
                channel_html = f"<p><strong>Channel:</strong> {channel_name}</p>"

        sections += f"""
        <hr>
        <img src="{v.get('thumbnail_r2_url', '')}" style="max-width:100%;"><br>
        <h2>{v.get('title', '')}</h2>
        {channel_html}
        <p><strong>Published:</strong> {v.get('published_at', '')}</p>
        <p><strong>Views:</strong> {v.get('metadata', {}).get('view_count', 'N/A')} &nbsp;
           <strong>Likes:</strong> {v.get('metadata', {}).get('like_count', 'N/A')}</p>
        <h3>Transcript</h3>
        {transcript_html}
        """

    html = f"""
    <html><body style="font-family: sans-serif; padding: 2rem;">
      <h1>Topic: {topic.get('name', '')}</h1>
      {sections}
    </body></html>
    """
    return HTML(string=html).write_pdf()
