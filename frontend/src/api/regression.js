import http from './http'

export const regressionOptions = () => http.get('/regression/options')
export const previewRegression = selection => http.post('/regression/preview', selection)
export const runSelectedRegression = selection => http.post('/regression/run', selection, { timeout: 600000 })

// 回归是触发型:不传 case_ids 则跑全部;返回汇总 {passed,total,passed_count,failed_count,pass_rate,interface_coverage,results}
export const runRegression = ({ envId, tag, notify } = {}) =>
  http.post('/regression', null, {
    params: {
      ...(envId ? { env_id: envId } : {}),
      ...(tag ? { tag } : {}),
      ...(notify ? { notify: true } : {}),
    },
  })
