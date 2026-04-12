import { useState, useEffect, useRef } from 'react'
import './App.css'
import SearchIcon from './assets/mag.png'
import { CourseSuggestion, Schedule } from './types'

const ALL_DISTRIBUTIONS = [
  'ALC', 'BIO', 'ETM', 'FLOPI', 'GLC',
  'HST', 'PHS', 'SCD', 'SDS', 'SMR', 'SSC',
]
const CAL_DAYS = ['M', 'T', 'W', 'R', 'F']
const CAL_DAY_LABELS: Record<string, string> = {
  M: 'Mon',
  T: 'Tue',
  W: 'Wed',
  R: 'Thu',
  F: 'Fri',
}
const DEFAULT_CAL_START_MIN = 8 * 60
const DEFAULT_CAL_END_MIN = 21 * 60
const COURSE_EVENT_COLORS = [
  { bg: '#fdebec', border: '#f2bec4', text: '#7a1f2b' },
  { bg: '#fdf3e8', border: '#f2d0ae', text: '#7a3e1e' },
  { bg: '#eef6fd', border: '#bfd9f3', text: '#1f466d' },
  { bg: '#edf9f1', border: '#bbdfc7', text: '#1d5b34' },
  { bg: '#f3eefc', border: '#d0c2ee', text: '#47327d' },
  { bg: '#fff6e6', border: '#ecd8a4', text: '#6a4d1b' },
]

type CalendarEvent = {
  day: string
  startMin: number
  endMin: number
  label: string
  courseId: string
}

const timeToMinutes = (t: string): number | null => {
  if (!t || t === 'TBA') return null
  const [h, m] = t.split(':').map(Number)
  if (Number.isNaN(h) || Number.isNaN(m)) return null
  return h * 60 + m
}

const hashCourseId = (courseId: string): number => {
  let hash = 0
  for (let i = 0; i < courseId.length; i += 1) {
    hash = (hash * 31 + courseId.charCodeAt(i)) >>> 0
  }
  return hash
}

function App(): JSX.Element {
  // Course input
  const [courseQuery, setCourseQuery] = useState('')
  const [suggestions, setSuggestions] = useState<CourseSuggestion[]>([])
  const [selectedCourses, setSelectedCourses] = useState<CourseSuggestion[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const suggestionsRef = useRef<HTMLDivElement>(null)

  // Distributions
  const [selectedDists, setSelectedDists] = useState<Set<string>>(new Set())

  // Professor preference query
  const [profQuery, setProfQuery] = useState('')

  // Scoring weights
  const [wSim, setWSim] = useState(0.5)
  const [wRating, setWRating] = useState(0.3)
  const [wDifficulty, setWDifficulty] = useState(0.2)
  const [difficultyFilter, setDifficultyFilter] = useState<string>('')

  // Results
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [totalSchedules, setTotalSchedules] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expandedCalendars, setExpandedCalendars] = useState<Set<number>>(new Set())

  // Close suggestions on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (suggestionsRef.current && !suggestionsRef.current.contains(e.target as Node)) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Course search autocomplete
  useEffect(() => {
    if (courseQuery.trim().length < 2) { setSuggestions([]); return }
    const timer = setTimeout(async () => {
      const resp = await fetch(`/api/courses/search?q=${encodeURIComponent(courseQuery)}`)
      const data: CourseSuggestion[] = await resp.json()
      const addedIds = new Set(selectedCourses.map(c => c.course_id))
      setSuggestions(data.filter(c => !addedIds.has(c.course_id)))
      setShowSuggestions(true)
    }, 200)
    return () => clearTimeout(timer)
  }, [courseQuery, selectedCourses])

  const addCourse = (course: CourseSuggestion) => {
    setSelectedCourses(prev => [...prev, course])
    setCourseQuery('')
    setSuggestions([])
    setShowSuggestions(false)
  }

  const removeCourse = (courseId: string) => {
    setSelectedCourses(prev => prev.filter(c => c.course_id !== courseId))
  }

  const toggleDist = (dist: string) => {
    setSelectedDists(prev => {
      const next = new Set(prev)
      if (next.has(dist)) next.delete(dist)
      else next.add(dist)
      return next
    })
  }

  const generateSchedules = async () => {
    if (selectedCourses.length < 2) {
      setError('Add at least 2 required courses.')
      return
    }
    setError('')
    setLoading(true)
    setSchedules([])
    setExpandedCalendars(new Set())

    const resp = await fetch('/api/schedules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        required_course_ids: selectedCourses.map(c => c.course_id),
        distributions: Array.from(selectedDists),
        query: profQuery,
        w_sim: wSim,
        w_rating: wRating,
        w_difficulty: wDifficulty,
        difficulty_filter: difficultyFilter,
        top_n: 10,
      }),
    })

    const data = await resp.json()
    if (data.error) {
      setError(data.error)
    } else {
      setSchedules(data.schedules || [])
      setTotalSchedules(data.total || 0)
    }
    setLoading(false)
  }

  const toggleCalendar = (rank: number) => {
    setExpandedCalendars(prev => {
      const next = new Set(prev)
      if (next.has(rank)) next.delete(rank)
      else next.add(rank)
      return next
    })
  }

  const buildCalendarEvents = (sched: Schedule): CalendarEvent[] => {
    const events: CalendarEvent[] = []
    sched.courses.forEach(course => {
      course.meetings
        .filter(m => m.days && m.days !== 'TBA')
        .forEach(m => {
          const startMin = timeToMinutes(m.start)
          const endMin = timeToMinutes(m.end)
          if (startMin === null || endMin === null || endMin <= startMin) return
          m.days.split('').forEach(day => {
            if (!CAL_DAYS.includes(day)) return
            events.push({
              day,
              startMin,
              endMin,
              label: `${course.course_id} (${m.type})`,
              courseId: course.course_id,
            })
          })
        })
    })
    return events
  }

  return (
    <div className="full-body-container">
      <header className="top-text">
        <span className="brand-pill">Cornell Schedule Builder</span>
        <h1 className="brand-title">Big Red Planner</h1>
        <p className="subtitle">Pick must-have classes, tune your priorities, and generate your best schedules.</p>
      </header>

      <main className="planner-layout">
        <section className="planner-main-column">
          <div className="section-panel">
            <div className="section-heading-row">
              <h3 className="section-title">Required Courses</h3>
              <span className="section-meta">{selectedCourses.length} selected (min 2)</span>
            </div>
            <p className="section-help-text">
              Add the classes you must take this term. We build every generated schedule around these courses.
            </p>

            <div className="course-search-wrapper" ref={suggestionsRef}>
              <div className="input-box">
                <img src={SearchIcon} alt="search" />
                <input
                  placeholder="Search courses by ID or title (e.g. CS 2110)"
                  value={courseQuery}
                  onChange={(e) => setCourseQuery(e.target.value)}
                  onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                />
              </div>
              {showSuggestions && suggestions.length > 0 && (
                <div className="suggestions-dropdown">
                  {suggestions.map(c => (
                    <div
                      key={c.course_id}
                      className="suggestion-item"
                      onClick={() => addCourse(c)}
                    >
                      <span className="suggestion-id">{c.course_id}</span>
                      <span className="suggestion-title">{c.title}</span>
                      <span className="suggestion-credits">{c.credits} cr</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="course-chips">
              {selectedCourses.map(c => (
                <div key={c.course_id} className="course-chip">
                  <span>{c.course_id}</span>
                  <button onClick={() => removeCourse(c.course_id)}>&times;</button>
                </div>
              ))}
            </div>
          </div>

          <div className="section-panel">
            <div className="section-heading-row">
              <h3 className="section-title">Distribution Preferences</h3>
              <span className="section-meta">{selectedDists.size} selected</span>
            </div>
            <p className="section-help-text">
              Optional filters. Added courses are chosen to match selected distribution categories.
            </p>
            <div className="dist-grid">
              {ALL_DISTRIBUTIONS.map(d => (
                <label key={d} className={`dist-chip ${selectedDists.has(d) ? 'active' : ''}`}>
                  <input
                    type="checkbox"
                    checked={selectedDists.has(d)}
                    onChange={() => toggleDist(d)}
                  />
                  {d}
                </label>
              ))}
            </div>
          </div>
        </section>

        <aside className="planner-side-column">
          <div className="section-panel">
            <h3 className="section-title">Professor Style</h3>
            <p className="section-help-text">
              Describe your preferred teaching style. This text is compared with professor reviews for ranking.
            </p>
            <div className="input-box">
              <img src={SearchIcon} alt="search" />
              <input
                placeholder="Helpful, clear lectures, engaging, fair grading..."
                value={profQuery}
                onChange={(e) => setProfQuery(e.target.value)}
              />
            </div>
          </div>

        <div className="section-panel">
            <h3 className="section-title">Scoring Weights</h3>
            <p className="section-help-text">
              Set how much each factor matters in ranking: review-match, overall rating, and difficulty.
            </p>
            <div className="weights-grid">
              <div className="weight-control">
                <label>Review Similarity</label>
                <input type="range" min="0" max="1" step="0.05" value={wSim}
                  onChange={(e) => setWSim(parseFloat(e.target.value))} />
                <span className="weight-value">{wSim.toFixed(2)}</span>
              </div>
              <div className="weight-control">
                <label>Rating</label>
                <input type="range" min="0" max="1" step="0.05" value={wRating}
                  onChange={(e) => setWRating(parseFloat(e.target.value))} />
                <span className="weight-value">{wRating.toFixed(2)}</span>
              </div>
              <div className="weight-control">
                <label>Difficulty</label>
                <input type="range" min="0" max="1" step="0.05" value={wDifficulty}
                  onChange={(e) => setWDifficulty(parseFloat(e.target.value))} />
                <span className="weight-value">{wDifficulty.toFixed(2)}</span>
              </div>
            </div>
          </div>

          <div className="section-panel">
          <h3 className="section-title">Schedule Difficulty</h3>
          <div className="dist-grid">
            {['easy', 'medium', 'hard'].map(level => (
              <label key={level} className={`dist-chip ${difficultyFilter === level ? 'active' : ''}`}>
                <input
                  type="radio"
                  name="difficulty"
                  checked={difficultyFilter === level}
                  onChange={() => setDifficultyFilter(level)}
                />
                {level.charAt(0).toUpperCase() + level.slice(1)}
              </label>
            ))}
          </div>
        </div>

          <div className="section-panel action-panel">
            <p className="section-help-text">
              Generate up to 10 ranked schedules. Use each card&apos;s calendar button to inspect weekly timing.
            </p>
            <div className="planner-stats">
              <div className="stat-item">
                <span className="stat-label">Courses</span>
                <span className="stat-value">{selectedCourses.length}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Distributions</span>
                <span className="stat-value">{selectedDists.size}</span>
              </div>
            </div>
            <button
              className="generate-btn"
              onClick={generateSchedules}
              disabled={loading || selectedCourses.length < 2}
            >
              {loading ? 'Generating…' : 'Generate Schedules'}
            </button>
            {error && <p className="error-msg">{error}</p>}
          </div>
        </aside>
      </main>

      {/* ── Schedule Results ─────────────────────── */}
      {schedules.length > 0 && (
        <div className="results-container">
          <h2 className="results-heading">
            Top {schedules.length} of {totalSchedules} schedules
          </h2>

          {schedules.map(sched => {
            const calendarEvents = buildCalendarEvents(sched)
            const latestEnd = calendarEvents.length > 0
              ? Math.max(...calendarEvents.map(e => e.endMin))
              : DEFAULT_CAL_END_MIN
            const calEndMin = Math.max(
              DEFAULT_CAL_END_MIN,
              Math.ceil((latestEnd + 30) / 60) * 60,
            )
            const calStartMin = DEFAULT_CAL_START_MIN
            const calRange = calEndMin - calStartMin
            const hourLabels = []
            for (let h = calStartMin / 60; h <= calEndMin / 60; h += 2) {
              hourLabels.push(h)
            }

            return (
              <div key={sched.rank} className="schedule-card">
                <div className="schedule-header">
                  <div>
                    <span className="schedule-rank">#{sched.rank}</span>
                    <span className="schedule-credits">{sched.total_credits} credits</span>
                  </div>
                  <div className="schedule-score-badge">
                    {(sched.score * 100).toFixed(1)}
                  </div>
                </div>

                {sched.score_breakdown && (
                  <div className="score-breakdown-panel">
                    <p className="score-breakdown-title">
                      Why this score: {(sched.score * 100).toFixed(1)} / 100
                    </p>
                    <p className="score-breakdown-text">{sched.score_breakdown.explanation}</p>
                    <div className="score-formula-grid">
                      <span>
                        Similarity: {sched.score_breakdown.weights.similarity.toFixed(2)} ×{' '}
                        {sched.score_breakdown.components.similarity.toFixed(2)} ={' '}
                        {sched.score_breakdown.weighted_components.similarity.toFixed(2)}
                      </span>
                      <span>
                        Rating: {sched.score_breakdown.weights.rating.toFixed(2)} ×{' '}
                        {sched.score_breakdown.components.rating.toFixed(2)} ={' '}
                        {sched.score_breakdown.weighted_components.rating.toFixed(2)}
                      </span>
                      <span>
                        Difficulty: {sched.score_breakdown.weights.difficulty.toFixed(2)} ×{' '}
                        {sched.score_breakdown.components.difficulty.toFixed(2)} ={' '}
                        {sched.score_breakdown.weighted_components.difficulty.toFixed(2)}
                      </span>
                    </div>
                    <div className="course-score-chips">
                      {sched.score_breakdown.course_breakdown.map(c => (
                        <span key={c.course_id} className="course-score-chip">
                          {c.course_id}: {(c.score * 100).toFixed(1)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="schedule-actions">
                  <button
                    className="calendar-toggle-btn"
                    onClick={() => toggleCalendar(sched.rank)}
                  >
                    {expandedCalendars.has(sched.rank) ? 'Hide Weekly Calendar' : 'Show Weekly Calendar'}
                  </button>
                </div>

                {expandedCalendars.has(sched.rank) && (
                  <div className="calendar-view">
                    <div className="calendar-time-col">
                      {hourLabels.map(hour => (
                        <span key={hour}>{hour}:00</span>
                      ))}
                    </div>
                    <div className="calendar-days">
                      {CAL_DAYS.map(day => {
                        const dayEvents = calendarEvents
                          .filter(e => e.day === day)
                          .sort((a, b) => a.startMin - b.startMin)
                        return (
                          <div key={day} className="calendar-day-col">
                            <div className="calendar-day-label">{CAL_DAY_LABELS[day]}</div>
                            <div className="calendar-day-track">
                              {dayEvents.map((event, idx) => {
                                const topPct = ((event.startMin - calStartMin) / calRange) * 100
                                const heightPct = ((event.endMin - event.startMin) / calRange) * 100
                                const swatch = COURSE_EVENT_COLORS[
                                  hashCourseId(event.courseId) % COURSE_EVENT_COLORS.length
                                ]
                                return (
                                  <div
                                    key={`${event.label}-${idx}`}
                                    className="calendar-event"
                                    style={{
                                      top: `${Math.max(0, topPct)}%`,
                                      height: `${Math.max(7, heightPct)}%`,
                                      background: swatch.bg,
                                      borderColor: swatch.border,
                                      color: swatch.text,
                                    }}
                                  >
                                    {event.label}
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                <div className="schedule-courses">
                  {sched.courses.map(course => (
                    <div key={course.course_id} className="sched-course">
                      <div className="sched-course-header">
                        <span className="sched-course-id">{course.course_id}</span>
                        <span className="sched-course-title">{course.title}</span>
                      </div>
                      <div className="sched-course-meta">
                        {course.instructors.length > 0 && (
                          <span>Instructors: {course.instructors.join(', ')}</span>
                        )}
                        <span>{course.credits} cr</span>
                        {course.distributions.length > 0 && (
                          <span>{course.distributions.join(', ')}</span>
                        )}
                      </div>
                      <div className="sched-course-meetings">
                        {course.meetings
                          .filter(m => m.days !== 'TBA')
                          .map((m, i) => (
                            <span key={i} className="meeting-tag">
                              {m.type} {m.days} {m.start}–{m.end}
                            </span>
                          ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default App
