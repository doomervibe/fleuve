import { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

const SHORTCUTS = [
  { keys: 'g d', label: 'Go to Dashboard' },
  { keys: 'g w', label: 'Go to Workflows' },
  { keys: 'g e', label: 'Go to Events' },
  { keys: 'g a', label: 'Go to Activities' },
  { keys: 'g t', label: 'Go to Delays' },
  { keys: '/', label: 'Focus search' },
  { keys: '?', label: 'Show this help' },
  { keys: 'Esc', label: 'Close modal' },
];

export function useKeyboardShortcuts({ onFocusSearch, onEscape } = {}) {
  const navigate = useNavigate();
  const [helpOpen, setHelpOpen] = useState(false);
  const keySequenceRef = useRef([]);
  const timeoutRef = useRef(null);

  const clearSequence = useCallback(() => {
    keySequenceRef.current = [];
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === '?') {
        e.preventDefault();
        setHelpOpen((o) => !o);
        return;
      }

      if (e.key === 'Escape') {
        if (helpOpen) {
          setHelpOpen(false);
        } else {
          onEscape?.();
          window.dispatchEvent(new CustomEvent('fleuve:closeModal'));
        }
        return;
      }

      if (e.key === '/' && !helpOpen) {
        e.preventDefault();
        onFocusSearch?.();
        return;
      }

      const key = e.key.toLowerCase();
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
        if (key === 'g' || key === 'd' || key === 'w' || key === 'e' || key === 'a' || key === 't') {
          return;
        }
      }

      if (key === 'g') {
        e.preventDefault();
        keySequenceRef.current = ['g'];
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(clearSequence, 800);
        return;
      }

      if (keySequenceRef.current.length === 1 && keySequenceRef.current[0] === 'g') {
        const routes = { d: '/', w: '/workflows', e: '/events', a: '/activities', t: '/delays' };
        if (routes[key]) {
          e.preventDefault();
          navigate(routes[key]);
        }
        clearSequence();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [helpOpen, onFocusSearch, onEscape, navigate, clearSequence]);

  return { helpOpen, setHelpOpen, shortcuts: SHORTCUTS };
}
