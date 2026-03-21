export interface CourseSuggestion {
  course_id: string;
  title: string;
  credits: number;
  distributions: string[];
}

export interface ScheduleMeeting {
  type: string;
  days: string;
  start: string;
  end: string;
}

export interface ScheduleCourse {
  course_id: string;
  title: string;
  credits: number;
  distributions: string[];
  instructors: string[];
  meetings: ScheduleMeeting[];
}

export interface Schedule {
  rank: number;
  score: number;
  total_credits: number;
  courses: ScheduleCourse[];
}
