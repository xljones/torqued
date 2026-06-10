import { useId } from 'react';

/** Text input with native datalist suggestions (e.g. garage names, categories). */
export default function SuggestInput({ value, onChange, options = [], placeholder, autoFocus }) {
  const listId = useId();
  return (
    <>
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        autoComplete="off"
        list={listId}
      />
      <datalist id={listId}>
        {options.map(opt => <option key={opt} value={opt} />)}
      </datalist>
    </>
  );
}
