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

export interface ScheduleCourseScoreBreakdown {
  course_id: string;
  title: string;
  score: number;
  matched_professors: number;
  explanation: string;
}

export interface ScheduleScoreBreakdown {
  weights: {
    similarity: number;
    rating: number;
    difficulty: number;
  };
  components: {
    similarity: number;
    rating: number;
    difficulty: number;
  };
  weighted_components: {
    similarity: number;
    rating: number;
    difficulty: number;
  };
  explanation: string;
  course_breakdown: ScheduleCourseScoreBreakdown[];
}

export interface Schedule {
  rank: number;
  score: number;
  total_credits: number;
  courses: ScheduleCourse[];
  score_breakdown?: ScheduleScoreBreakdown;
}
