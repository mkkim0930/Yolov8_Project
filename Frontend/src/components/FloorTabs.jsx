import { FLOORS } from '../constants';

export default function FloorTabs({ selectedFloor, onChange }) {
  return (
    <section className="floor-section">
      <div className="section-heading">
        <h3>열람실</h3>
        <p>확인할 층 선택</p>
      </div>

      <div className="floor-tabs">
        {FLOORS.map((floor) => (
          <button
            key={floor}
            className={`floor-tab ${
              selectedFloor === floor ? 'active' : ''
            }`}
            onClick={() => onChange(floor)}
          >
            {floor}층
          </button>
        ))}
      </div>
    </section>
  );
}
