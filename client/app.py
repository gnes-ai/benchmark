import datetime
import json
import os
from math import ceil

import numpy as np
from gnes.cli.parser import set_client_cli_parser
from gnes.client.cli import CLIClient
from gnes.helper import get_duration
from gnes.proto import gnes_pb2
from google.protobuf.json_format import Parse


class MyClient(CLIClient):

    @property
    def bytes_generator(self):
        for _ in range(self.args.num_docs):
            yield b'a' * self.args.num_bytes

    def analyze(self):
        num_effective_lines = ceil(self.args.num_docs / self.args.batch_size)
        summary = {}
        with open('/workspace/network.json') as fp:
            infos = [Parse(v, gnes_pb2.Envelope()).routes for v in fp.readlines()[-num_effective_lines:]]
            summary['f:send interval'] = [get_duration(infos[j][0].start_time, infos[j + 1][0].start_time) for j in
                                          range(len(infos) - 1)]
            summary['f:recv interval'] = [get_duration(infos[j][0].end_time, infos[j + 1][0].end_time) for j in
                                          range(len(infos) - 1)]
            summary['f->r1 trans'] = [get_duration(j[0].start_time, j[1].start_time) for j in infos]
            summary['r1->r2 trans'] = [get_duration(j[1].end_time, j[2].start_time) for j in infos]
            summary['r2->f trans'] = [get_duration(j[2].end_time, j[0].end_time) for j in infos]
            summary['roundtrip'] = [get_duration(j[0].start_time, j[0].end_time) for j in infos]

        print('%40s\t%6s\t%6s\t%6s\t%6s\t%6s' % ('measure', 'mean', 'std', 'median', 'max', 'min'))

        for k, v in summary.items():
            print('%40s\t%3.3fs (+-%2.2f)\t%3.3fs\t%3.3fs\t%3.3fs' % (
                k, np.mean(v), np.std(v), np.median(v), np.max(v), np.min(v)))

        return {k: np.mean(v) for k, v in summary.items()}


if __name__ == '__main__':
    parser = set_client_cli_parser()
    parser.add_argument('--num_bytes', type=int, default=10,
                        help='number of bytes per doc')
    parser.add_argument('--num_docs', type=int, default=10,
                        help='number of docs in total')
    parser.add_argument('--retries', type=int, default=3,
                        help='number of retries')
    args = parser.parse_args()

    all_summaries = []
    for _ in range(args.retries):
        m = MyClient(args)
        all_summaries.append(m.analyze())

    print('%40s\t%6s\t%6s\t%6s' % ('measure', 'best', 'worst', 'avg'))
    final = {'version': os.environ.get('GNES_IMG_TAG', 'unknown'),
             'timestamp': datetime.datetime.now().timestamp()}
    for k in all_summaries[0].keys():
        worst = np.max([j[k] for j in all_summaries])
        best = np.min([j[k] for j in all_summaries])
        avg = np.mean([j[k] for j in all_summaries])
        print('%40s\t%3.3fs\t%3.3fs\t%3.3fs' % (k, best, worst, avg))
        final[k] = float(best)

    with open('/workspace/history%s.json' % os.environ.get('GNES_BENCHMARK_ID'), 'a', encoding='utf8') as fp:
        fp.write(json.dumps(final, ensure_ascii=False, sort_keys=True) + '\n')
