import { useState, useEffect, useRef } from 'react'
import './App.css'
import SearchIcon from './assets/mag.png'
import { CourseSuggestion, Schedule } from './types'

const ALL_DISTRIBUTIONS = [
  'ALC', 'BIO', 'ETM', 'FLOPI', 'GLC',
  'HST', 'PHS', 'SCD', 'SDS', 'SMR', 'SSC',
]

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

  return (
    <div className="full-body-container">
      {/* Header */}
      <div className="top-text">
        <div className="google-colors">
          <h1 id="google-4">4</h1>
          <h1 id="google-3">3</h1>
          <h1 id="google-0-1">0</h1>
          <h1 id="google-0-2">0</h1>
        </div>
        <p className="subtitle">Big Red Planner</p>
      </div>

      <div className="controls-container">
        {/* ── Required Courses ──────────────────────── */}
        <div className="section-panel">
          <h3 className="section-title">Required Courses (min. 2)</h3>

          <div className="course-chips">
            {selectedCourses.map(c => (
              <div key={c.course_id} className="course-chip">
                <span>{c.course_id}</span>
                <button onClick={() => removeCourse(c.course_id)}>&times;</button>
              </div>
            ))}
          </div>

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
        </div>

        {/* ── Distributions ────────────────────────── */}
        <div className="section-panel">
          <h3 className="section-title">Distribution Requirements</h3>
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

        {/* ── Professor Preference ─────────────────── */}
        <div className="section-panel">
          <h3 className="section-title">Professor Preference</h3>
          <div className="input-box">
            <img src={SearchIcon} alt="search" />
            <input
              placeholder="Describe your ideal professor (e.g. helpful, clear lectures)"
              value={profQuery}
              onChange={(e) => setProfQuery(e.target.value)}
            />
          </div>
        </div>

        {/* ── Scoring Weights ──────────────────────── */}
        <div className="section-panel">
          <h3 className="section-title">Scoring Weights</h3>
          <div className="weights-grid">
            <div className="weight-control">
              <label>Weighting of Query</label>
              <input type="range" min="0" max="1" step="0.05" value={wSim}
                onChange={(e) => setWSim(parseFloat(e.target.value))} />
              <span className="weight-value">{wSim.toFixed(2)}</span>
            </div>
            <div className="weight-control">
              <label>Professor Preference</label>
              <input type="range" min="0" max="1" step="0.05" value={wRating}
                onChange={(e) => setWRating(parseFloat(e.target.value))} />
              <span className="weight-value">{wRating.toFixed(2)}</span>
            </div>
            <div className="weight-control">
              <label>Difficulty Weighting</label>
              <input type="range" min="0" max="1" step="0.05" value={wDifficulty}
                onChange={(e) => setWDifficulty(parseFloat(e.target.value))} />
              <span className="weight-value">{wDifficulty.toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* ── Difficulty Weighting ──────────────────────── */}
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

        {/* ── Generate Button ──────────────────────── */}
        <button
          className="generate-btn"
          onClick={generateSchedules}
          disabled={loading || selectedCourses.length < 2}
        >
          {loading ? 'Generating…' : 'Generate Schedules'}
        </button>

        {error && <p className="error-msg">{error}</p>}
      </div>

      {/* ── Schedule Results ─────────────────────── */}
      {schedules.length > 0 && (
        <div className="results-container">
          <h2 className="results-heading">
            Top {schedules.length} of {totalSchedules} schedules
          </h2>

          {schedules.map(sched => (
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
          ))}
        </div>
      )}
    </div>
  )
}

export default App
