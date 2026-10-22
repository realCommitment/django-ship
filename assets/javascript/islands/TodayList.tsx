import { useState } from 'react';
import type { FormEvent } from 'react';

type Task = { id: number; text: string; done: boolean };

// The productivity landing page's demo island: plan a few things for today, kept in the browser only.
export default function TodayList({ limit = 3 }: { limit?: number }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [text, setText] = useState<string>('');

  function add(event: FormEvent): void {
    event.preventDefault();
    const trimmed: string = text.trim();
    if (!trimmed || tasks.length >= limit) {
      return;
    }
    setTasks([...tasks, { id: tasks.length, text: trimmed, done: false }]);
    setText('');
  }

  function toggle(id: number): void {
    setTasks(tasks.map((task: Task) => (task.id === id ? { ...task, done: !task.done } : task)));
  }

  return (
    <form className="card bg-base-100 shadow-sm text-left" onSubmit={add}>
      <div className="card-body gap-3">
        <h2 className="card-title">Plan your day</h2>
        <ul className="space-y-2">
          {tasks.map((task: Task) => (
            <li key={task.id}>
              <label className="flex items-center gap-3">
                <input type="checkbox" className="checkbox" checked={task.done} onChange={() => toggle(task.id)} />
                <span className={task.done ? 'line-through opacity-60' : ''}>{task.text}</span>
              </label>
            </li>
          ))}
        </ul>
        {tasks.length < limit ? (
          <div className="join w-full">
            <input
              className="input join-item w-full"
              placeholder={`Thing ${tasks.length + 1} of ${limit}`}
              aria-label="New task"
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
            <button type="submit" className="btn btn-primary join-item">Add</button>
          </div>
        ) : (
          <p className="text-sm opacity-70">That's {limit}. Now go do them.</p>
        )}
      </div>
    </form>
  );
}
