import http from './http'

// 回归是触发型:不传 case_ids 则跑全部;返回汇总 {passed,total,passed_count,failed_count,pass_rate,interface_coverage,results}
export const runRegression = ({ envId, tag, notify } = {}) =>
  http.post('/regression', null, {
    params: {
      ...(envId ? { env_id: envId } : {}),
      ...(tag ? { tag } : {}),
      ...(notify ? { notify: true } : {}),
    },
  })
