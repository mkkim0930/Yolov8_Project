import { useEffect } from 'react';

// 알림 신청 결과(완료/실패) 팝업
export default function AlertModal({ title, message, error, onClose }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={`modal-icon ${error ? 'error' : ''}`}>
          {error ? '!' : '✓'}
        </div>
        <h4>{title}</h4>
        <p>{message}</p>
        <button className="modal-confirm" onClick={onClose}>
          확인
        </button>
      </div>
    </div>
  );
}
