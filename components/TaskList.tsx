
import React from 'react';
import { Task, Priority } from '../types';
import { TrashIcon, CheckIcon } from './icons';

interface TaskListProps {
  tasks: Task[];
  onToggle: (id: number) => void;
  onDelete: (id: number) => void;
}

const priorityConfig: Record<Priority, { bg: string; text: string; dot: string; border: string }> = {
  Low: { bg: 'bg-blue-50 dark:bg-blue-900/20', text: 'text-blue-700 dark:text-blue-300', dot: 'bg-blue-500', border: 'border-blue-200 dark:border-blue-800' },
  Medium: { bg: 'bg-amber-50 dark:bg-amber-900/20', text: 'text-amber-700 dark:text-amber-300', dot: 'bg-amber-500', border: 'border-amber-200 dark:border-amber-800' },
  High: { bg: 'bg-red-50 dark:bg-red-900/20', text: 'text-red-700 dark:text-red-300', dot: 'bg-red-500', border: 'border-red-200 dark:border-red-800' },
};

const TaskList: React.FC<TaskListProps> = ({ tasks, onToggle, onDelete }) => {
  if (tasks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-xl">
        <p className="text-gray-500 dark:text-gray-400 font-medium">No tasks yet</p>
        <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">Add a task above to get started</p>
      </div>
    );
  }

  return (
    <ul className="space-y-3">
      {tasks.map((task) => {
        const config = priorityConfig[task.priority];
        return (
          <li
            key={task.id}
            className={`group flex items-center justify-between p-4 rounded-xl bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 shadow-sm transition-all duration-200 hover:shadow-md ${task.completed ? 'opacity-75' : ''}`}
          >
            <div className="flex items-start gap-4 overflow-hidden w-full">
               <button
                onClick={() => onToggle(task.id)}
                className={`flex-shrink-0 w-5 h-5 mt-0.5 rounded border transition-colors flex items-center justify-center ${
                  task.completed
                    ? 'bg-primary-600 border-primary-600 text-white'
                    : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-500 hover:border-primary-500'
                }`}
              >
                {task.completed && <CheckIcon size={12} strokeWidth={3} />}
              </button>
              
              <div className="flex flex-col gap-1.5 overflow-hidden w-full">
                <span
                  className={`text-sm font-medium truncate transition-all duration-200 ${
                    task.completed ? 'line-through text-gray-400 dark:text-gray-500' : 'text-gray-800 dark:text-gray-200'
                  }`}
                >
                  {task.text}
                </span>
                
                <div className="flex">
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${config.bg} ${config.text} ${config.border}`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${config.dot}`}></span>
                    {task.priority}
                  </span>
                </div>
              </div>
            </div>
            
            <button
              onClick={() => onDelete(task.id)}
              className="ml-2 p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-all opacity-0 group-hover:opacity-100 focus:opacity-100"
              aria-label="Delete task"
            >
              <TrashIcon size={16} />
            </button>
          </li>
        );
      })}
    </ul>
  );
};

export default TaskList;
