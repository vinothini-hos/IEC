"""
Sends the clarification email drafted by template_consolidation.py, reusing
the same Gmail send + resync path as a normal reply (see routers/emails.py).
Attaches the SO2/CL2 query-sheet template filled with the extracted values
(see spec_template.py).
"""

from sqlalchemy.orm import Session

from . import gmail_service, spec_template, sync_service


def send_clarification(db: Session, thread, equipment_index: int) -> dict:
    result = thread.extraction_result
    if not result or not result.get("equipment_items"):
        raise ValueError("No extraction result for this thread yet")

    items = result["equipment_items"]
    if equipment_index < 0 or equipment_index >= len(items):
        raise ValueError("Invalid equipment_index")

    item = items[equipment_index]
    draft = item.get("clarification_draft")
    if not draft:
        raise ValueError("No clarification needed for this equipment item")

    last_email = thread.latest_email
    in_reply_to = last_email.gmail_message_id if last_email else None

    filename, content = spec_template.fill_template_workbook(
        item["equipment_name"], item["type_label"], item["fields"], draft["recipient"]
    )
    attachments = None
    if content:
        attachments = [{
            "filename": filename,
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "content": content,
        }]

    sent = gmail_service.send_email(
        to=draft["recipient"],
        subject=draft["subject"],
        body_text=draft["body"],
        gmail_thread_id=thread.gmail_thread_id,
        in_reply_to_message_id=in_reply_to,
        attachments=attachments,
    )

    updated_thread = sync_service.upsert_thread_from_gmail(db, sent["threadId"])
    updated_thread.extraction_status = "waiting_for_customer_response"
    db.commit()

    return {
        "sent": True,
        "to": draft["recipient"],
        "subject": draft["subject"],
        "body": draft["body"],
        "status": updated_thread.extraction_status,
        "attachment_filename": filename,
    }