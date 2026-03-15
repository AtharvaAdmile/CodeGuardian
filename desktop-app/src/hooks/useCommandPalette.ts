import { useState, useCallback, useEffect } from "react";

interface CommandItem {
  id: string;
  label: string;
  category: "navigation" | "action" | "recent" | "file";
  action: () => void;
  icon?: React.ReactNode;
}

interface UseCommandPaletteReturn {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  filteredItems: CommandItem[];
  selectedIndex: number;
  selectNext: () => void;
  selectPrev: () => void;
  executeSelected: () => void;
}

export function useCommandPalette(
  items: CommandItem[]
): UseCommandPaletteReturn {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  const filteredItems = searchQuery
    ? items.filter(
        (item) =>
          item.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
          item.category.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : items;

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => {
    setIsOpen(false);
    setSearchQuery("");
    setSelectedIndex(0);
  }, []);
  const toggle = useCallback(() => {
    if (isOpen) close();
    else open();
  }, [isOpen, open, close]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        toggle();
      }

      if (!isOpen) return;

      if (e.key === "Escape") {
        e.preventDefault();
        close();
      }

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) =>
          Math.min(prev + 1, filteredItems.length - 1)
        );
      }

      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
      }

      if (e.key === "Enter") {
        e.preventDefault();
        if (filteredItems[selectedIndex]) {
          filteredItems[selectedIndex].action();
          close();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, toggle, close, filteredItems, selectedIndex]);

  const selectNext = useCallback(() => {
    setSelectedIndex((prev) =>
      Math.min(prev + 1, filteredItems.length - 1)
    );
  }, [filteredItems.length]);

  const selectPrev = useCallback(() => {
    setSelectedIndex((prev) => Math.max(prev - 1, 0));
  }, []);

  const executeSelected = useCallback(() => {
    if (filteredItems[selectedIndex]) {
      filteredItems[selectedIndex].action();
      close();
    }
  }, [filteredItems, selectedIndex, close]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [searchQuery]);

  return {
    isOpen,
    open,
    close,
    toggle,
    searchQuery,
    setSearchQuery,
    filteredItems,
    selectedIndex,
    selectNext,
    selectPrev,
    executeSelected,
  };
}
