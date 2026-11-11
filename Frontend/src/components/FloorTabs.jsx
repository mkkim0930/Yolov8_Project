import { FLOORS } from '../constants';

export default function FloorTabs({ selectedFloor, onChange }) {
  return (
    <div className="nl-floors" role="tablist" aria-label="층 선택">
      {FLOORS.map((floor) => (
        <button
          key={floor}
          role="tab"
          aria-selected={selectedFloor === floor}
          className={selectedFloor === floor ? 'active' : ''}
          onClick={() => onChange(floor)}
        >
          {floor}층
        </button>
      ))}
    </div>
  );
}
