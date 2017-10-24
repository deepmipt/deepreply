import os
import shutil
import json
import urllib.parse
import urllib.request
import tarfile
import glob
import sys
import argparse
from datetime import datetime


def get_model_files(config):
    kpi_name = config['kpi_name']
    update_models = config['update_models']
    update_models_from_local = config['update_models_from_local']
    kpi_models_dir = os.path.join(config['models_dir'], kpi_name)
    model_repo_url = config['kpis'][kpi_name]['settings_kpi']['model_repo_url']
    model_filename = os.path.basename(urllib.parse.urlsplit(model_repo_url).path)
    model_download_path = os.path.join(kpi_models_dir, model_filename)
    model_extract_dir = model_download_path[:model_download_path.rfind(".tar.gz")] + '/'

    if update_models:
        # Delete existing extracted model files
        if os.path.isdir(model_extract_dir) and model_extract_dir != '/':
            print('Deleting existing extracted model files...')
            shutil.rmtree(model_extract_dir, ignore_errors=True)
            print('Done')

        # Download model files
        print('Downloading model to ' + model_download_path + ' ...')
        os.makedirs(os.path.dirname(model_extract_dir), exist_ok=True)
        if update_models_from_local:
            shutil.copy(model_repo_url, model_download_path)
        else:
            req = urllib.request.urlopen(model_repo_url)
            with open(model_download_path, 'w+b') as f:
                f.write(req.read())
                f.close()
        print('Done')

        # Extract model files
        print('Extracting model to ' + model_extract_dir + ' ...')
        tar = tarfile.open(model_download_path, 'r:gz')
        tar.extractall(path=model_extract_dir)
        tar.close()
        print('Done')

        # Delete downloaded model files
        if os.path.isfile(model_download_path) and model_download_path != '/':
            print('Deleting downloaded model files...')
            os.remove(model_download_path)
            print('Done')

    return model_extract_dir


def get_modelfiles_paths(model_dir, model_files):
    modelfiles_paths = []
    # Constructing full path to each model
    for file in model_files:
        search_tempalte = os.path.join(model_dir, file + '*')
        results = glob.glob(search_tempalte)
        if len(results) > 0:
            result = results[0]
            modelfiles_paths.append(os.path.join(os.path.dirname(result), file))
    return modelfiles_paths


def getopts(argv):
    parent_parser = argparse.ArgumentParser()
    parser = argparse.ArgumentParser(parents=[parent_parser], conflict_handler='resolve')
    parser.add_argument('-k', type=str, action='store', dest='k', default=None)
    parser.add_argument('-m', type=str, action='store', dest='m', default=None)
    parser.add_argument('-e', type=str, action='store', dest='e', default=None)
    parser.add_argument('-i', type=int, action='store', dest='i', default=None)
    parser.add_argument('-t', type=int, action='store', dest='t', default=None)
    parser.add_argument('-l', action='store_true', dest='l', default=False)
    args = parser.parse_args(argv)
    opt = {}
    opt['kpi_name'] = args.k
    opt['model_files_dir'] = args.m
    opt['embedding_file'] = args.e
    opt['iterations_num'] = args.i
    opt['test_tasks_number'] = args.t
    opt['log_tester_state'] = args.l
    return opt


def main(argv):
    opt = getopts(argv)

    # Initialise environment variables
    print('Reading environment variables...')
    opt['models_repo_url'] = os.getenv('MODELS_URL')
    opt['embeddings_repo_url'] = os.getenv('EMBEDDINGS_URL')
    opt['datasets_repo_url'] = os.getenv('DATASETS_URL')

    # Read config.json
    print('Reading config.json...')
    with open('config.json') as config_json:
        config = json.load(config_json)

    data_dir = config['data_dir']
    os.makedirs(os.path.dirname(data_dir), exist_ok=True)

    # Override config parameters if provided via command line
    if opt['kpi_name'] is not None:
        kpi_name = opt['kpi_name']
        config['kpi_name'] = opt['kpi_name']
        if opt['test_tasks_number'] is not None:
            config['kpis'][kpi_name]['settings_kpi']['test_tasks_number'] = opt['test_tasks_number']
    else:
        kpi_name = config['kpi_name']
        opt['model_files_dir'] = None
        opt['embedding_file'] = None

    if opt['iterations_num'] is not None:
        config['iterations_num'] = opt['iterations_num']

    if opt['log_tester_state'] is not None:
        config['log_tester_state'] = opt['log_tester_state']

    # Get model files dir [and update models files]
    model_files_dir = opt['model_files_dir'] if opt['model_files_dir'] is not None else get_model_files(config)

    # Get model files list
    opt['model_files'] = \
        get_modelfiles_paths(model_files_dir, config['kpis'][kpi_name]['settings_agent']['model_files_names'])

    # Execute test
    tester_module = __import__(config['kpis'][kpi_name]['settings_kpi']['tester_file'])
    tester_class = getattr(tester_module, 'Tester')
    tester = tester_class(config, opt)
    tester.init_agent()
    iters = config['iterations_num']
    log_tester_state = config['log_tester_state']
    for _ in range(iters):
        print('Executing %s test...' % config['kpi_name'])
        start_time = str(datetime.now())
        tester.run_test(init_agent=False)
        end_time = str(datetime.now())
        print('%s test finished, tasks number: %s, SCORE: %s' % (config['kpi_name'],
                                                                 str(tester.numtasks),
                                                                 str(tester.score)))

        # Log tester object state
        if log_tester_state:
            tester_state = 'tasks: %s' \
                           '\nobservations: %s' \
                           '\npredictions: %s' \
                           '\nanswers: %s' \
                           '\nresponse code: %s' % (tester.tasks,
                                                    tester.observations,
                                                    tester.predictions,
                                                    tester.answers,
                                                    tester.response_code)
        else:
            tester_state = ''

        # Log test results
        log_str = 'testing %s :' \
                  '\nsession id: %s' \
                  '\ntasks number: %s' \
                  '\nstart time: %s' \
                  '\nend time  : %s' \
                  '\nscore: %s' \
                  '\n\n%s' % (kpi_name,
                              tester.session_id,
                              tester.numtasks,
                              start_time,
                              end_time,
                              tester.score,
                              tester_state)

        file_path = os.path.join(config['test_logs_dir'], '%s_%s.txt' % (kpi_name, start_time))
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        f = open(file_path, 'w')
        f.write(log_str)
        f.close()


if __name__ == '__main__':
    main(sys.argv[1:])
