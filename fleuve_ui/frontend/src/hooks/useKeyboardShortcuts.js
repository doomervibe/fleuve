import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

const SHORTCUTS = {
  d: '/',
  e: '/events',
  a: '/activities',
  l: '/delays',
  r: '/runners',
};

function isFormElement(target) {
  const tag = target.tagName?.toLowerCase();
  return (
    tag === 'input' ||
    tag === 'textarea' ||
    tag === 'select' ||
    target.isContentEditable
  );
}

export function useKeyboardShortcuts() {
  const navigate = useNavigate();
  const goModeRef = useRef(false);
  const timeoutRef = useRef(null);

  useEffect(() => {
    function handleKeyDown(e) {
      if (isFormElement(e.target)) return;

      if (e.key === 'g' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        goModeRef.current = true;
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(() => {
          goModeRef.current = false;
          timeoutRef.current = null;
        }, 1000);
        return;
      }

      if (goModeRef.current) {
        const key = e.key?.toLowerCase();
        const path = SHORTCUTS[key];
        if (path) {
          e.preventDefault();
          goModeRef.current = false;
          if (timeoutRef.current) {
            clearTimeout(timeoutRef.current);
            timeoutRef.current = null;
          }
          navigate(path);
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [navigate]);
}
