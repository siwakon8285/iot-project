import { useEffect, useRef, useState } from "react";

import { SENSITIVITY_OPTIONS, type Sensitivity } from "../types/ai";

interface ProfileModalProps {
  initialSelection: Sensitivity[];
  canDismiss: boolean;
  onConfirm: (selection: Sensitivity[]) => void;
  onClose: () => void;
}

export function ProfileModal({
  initialSelection,
  canDismiss,
  onConfirm,
  onClose,
}: ProfileModalProps) {
  const [selection, setSelection] = useState<Sensitivity[]>(initialSelection);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.querySelector<HTMLButtonElement>(".profile-option")?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && canDismiss) {
        event.preventDefault();
        onClose();
      }
      if (event.key !== "Tab" || !dialogRef.current) {
        return;
      }
      const focusable = [...dialogRef.current.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [canDismiss, onClose]);

  function toggle(sensitivity: Sensitivity) {
    setSelection((current) => current.includes(sensitivity)
      ? current.filter((item) => item !== sensitivity)
      : [...current, sensitivity]);
  }

  return (
    <div className="modal-backdrop">
      <div
        ref={dialogRef}
        className="profile-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="profile-modal-title"
        aria-describedby="profile-modal-description profile-modal-instruction"
      >
        <div className="profile-modal__topline">
          <span className="profile-modal__mark" aria-hidden="true">✦</span>
          {canDismiss && (
            <button className="profile-modal__close" type="button" onClick={onClose} aria-label="ปิดหน้าต่างแก้ไขข้อมูลสุขภาพ">
              ×
            </button>
          )}
        </div>
        <p className="section-kicker">AI สำหรับคุณ</p>
        <h2 id="profile-modal-title">ผู้ช่วย AI วิเคราะห์สภาพแวดล้อมเพื่อสุขภาพ</h2>
        <p id="profile-modal-description" className="profile-modal__description">
          สวัสดีครับ ผมเป็นผู้ช่วย AI ที่จะช่วยวิเคราะห์ว่าสภาพแวดล้อมปัจจุบันเหมาะกับคุณหรือไม่ โดยอ้างอิงจากข้อมูลที่วัดได้และลักษณะสุขภาพที่คุณเลือก
        </p>
        <p id="profile-modal-instruction" className="profile-modal__instruction">
          กรุณาเลือกลักษณะที่ตรงกับสุขภาพของคุณอย่างน้อย 1 ข้อ
        </p>
        <div className="profile-options" role="group" aria-label="ลักษณะสุขภาพที่เลือกได้">
          {SENSITIVITY_OPTIONS.map(({ id, label }) => {
            const selected = selection.includes(id);
            return (
              <button
                key={id}
                className={`profile-option${selected ? " profile-option--selected" : ""}`}
                type="button"
                aria-pressed={selected}
                onClick={() => toggle(id)}
              >
                <span className="profile-option__check" aria-hidden="true">{selected ? "✓" : ""}</span>
                <span>{label}</span>
              </button>
            );
          })}
        </div>
        <div className="profile-modal__actions">
          {canDismiss && <button className="profile-modal__cancel" type="button" onClick={onClose}>ยกเลิก</button>}
          <button
            className="profile-modal__confirm"
            type="button"
            disabled={selection.length === 0}
            onClick={() => onConfirm(selection)}
          >
            ยืนยันและเริ่มวิเคราะห์
          </button>
        </div>
      </div>
    </div>
  );
}
