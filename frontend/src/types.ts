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

export interface LatentDimensionContribution {
  dimension: number;
  query_activation: number;
  schedule_activation: number;
  contribution: number;
  top_positive_terms: string[];
  top_negative_terms: string[];
}

export interface LatentExplainability {
  positive_dimensions: LatentDimensionContribution[];
  negative_dimensions: LatentDimensionContribution[];
}

export interface ScheduleScoreBreakdown {
  search_method?: "svd" | "tfidf";
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
  latent_explainability?: LatentExplainability | null;
}

export interface Schedule {
  rank: number;
  score: number;
  total_credits: number;
  courses: ScheduleCourse[];
  score_breakdown?: ScheduleScoreBreakdown;
}
