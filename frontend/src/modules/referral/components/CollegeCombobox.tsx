import { useEffect, useState } from "react";

import { useCollegeSearch } from "@/modules/referral/hooks";
import type { CollegeSearchResult } from "@/modules/referral/types";

interface Props {
  value: CollegeSearchResult | null;
  onChange: (selection: CollegeSearchResult | null) => void;
  placeholder?: string;
}

/**
 * Lightweight typeahead — input + fetched suggestions list. Doesn't
 * use shadcn's Combobox primitive yet (that ships when the rest of
 * shadcn primitives are scaffolded in S2). Sufficient for S1 demo.
 */
export function CollegeCombobox({
  value,
  onChange,
  placeholder = "Type college name (e.g. VIT)",
}: Props) {
  const [query, setQuery] = useState(value?.canonical_name ?? "");
  const [searchQuery, setSearchQuery] = useState("");
  const [open, setOpen] = useState(false);
  const search = useCollegeSearch(searchQuery);

  // When `value` is set from outside (e.g. AI resume parser auto-selects
  // a college) sync the visible text to the canonical name. Without this
  // the input stays empty while the form's `state.college` is set, which
  // makes it look like nothing happened.
  useEffect(() => {
    if (value !== null && query !== value.canonical_name) {
      setQuery(value.canonical_name);
    }
    // We intentionally only react to `value` changes; user typing is
    // handled in the input's onChange.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const selectAndClose = (college: CollegeSearchResult) => {
    onChange(college);
    setQuery(college.canonical_name);
    setOpen(false);
  };

  return (
    <div className="relative">
      <input
        id="college-combobox"
        type="text"
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        aria-controls="college-suggestions"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setSearchQuery("");
          setOpen(true);
          if (value !== null) onChange(null);
        }}
        onKeyDown={(e) => {
          if (e.key !== "Enter") return;
          e.preventDefault();
          const next = query.trim();
          if (next.length > 1) {
            setSearchQuery(next);
            setOpen(true);
          }
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 100)}
        placeholder={placeholder}
        className="flex h-9 w-full rounded-md border border-border bg-card px-3 py-2 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      />
      {open && query.trim().length > 0 && (
        <ul
          id="college-suggestions"
          role="listbox"
          className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md border border-border bg-popover text-popover-foreground shadow-lg"
        >
          {!searchQuery.trim() && query.trim().length > 1 && (
            <li className="px-3 py-2 text-sm text-muted-foreground">
              Press Enter to search for colleges.
            </li>
          )}
          {search.isLoading && (
            <li className="px-3 py-2 text-sm text-muted-foreground">Searching…</li>
          )}
          {search.data?.length === 0 && !search.isLoading && searchQuery.trim().length > 1 && (
            <li className="px-3 py-2 text-sm text-muted-foreground">
              No matches. Pick a similar college or contact HR to add a new one.
            </li>
          )}
          {search.data?.map((college) => (
            <li key={college.id} role="option" aria-selected={value?.id === college.id}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => selectAndClose(college)}
                className="flex w-full items-start justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-secondary"
              >
                <span>
                  <span className="font-medium">{college.canonical_name}</span>
                  {college.location_state !== null && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      {college.location_state}
                    </span>
                  )}
                  {college.aliases.length > 0 && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      ({college.aliases.slice(0, 2).join(", ")})
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
