import click
import sys
import json
import gettext
from ltldoorstep import printer
from ltldoorstep.config import load_config
from ltldoorstep.engines import engines
from ltldoorstep.context import DoorstepContext
import asyncio
import logging

LOGGING_FORMAT = '%(asctime)-15s %(message)s'

# TODO: possibly replace with e.g. dynaconf as needs evolve
def get_engine(engine, config):
    if ':' in engine:
        engine, engine_options = engine.split(':')
        sp = lambda x: (x.split('=') if '=' in x else (x, True))
        engine_options = {k: v for k, v in map(sp, engine_options.split(','))}
    else:
        engine_options = {}

    if 'engine' not in config:
        config['engine'] = {}

    for option, value in engine_options.items():
        config['engine'][option] = value

    return engine, config

@click.group()
@click.option('--debug/--no-debug', default=False)
@click.option('-b', '--bucket', default=None)
@click.option('-o', '--output', type=click.Choice(printer.get_printer_types()), default='ansi')
@click.option('--output-file', default=None)
@click.pass_context
def cli(ctx, debug, bucket, output, output_file):
    gettext.install('ltldoorstep')

    if output_file is None:
        output_file = sys.stdout

    prnt = printer.get_printer(output, debug, target=output_file)

    config = load_config()

    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format=LOGGING_FORMAT)
    logger = logging.getLogger(__name__)

    ctx.obj = {
        'DEBUG': debug,
        'printer': prnt,
        'config': config,
        'bucket': bucket,
        'logger': logger
    }

@cli.command(name='engine-info')
@click.argument('engine', required=False)
@click.pass_context
def engine_info(ctx, engine=None):
    if engine:
        if engine in engines:
            click.echo(_('Engine details: %s') % engine)
            click.echo(_('    %s') % engines[engine].description())
            click.echo()
            config_help = engines[engine].config_help()
            if config_help:
                for setting, description in config_help.items():
                    click.echo("%s:\n\t%s" % (setting, description.replace('\n', '\n\t')))
            else:
                click.echo("No configuration settings for this engine")
        else:
            click.echo(_('Engine not known'))
    else:
        click.echo(_('Engines available:') + ' ' + ', '.join(engines))

@cli.command()
@click.option('-e', '--engine', required=True)
@click.pass_context
def status(ctx, engine):
    debug = ctx.obj['DEBUG']
    click.echo(_('STATUS'))

    if debug:
        click.echo(_('Debug is on'))
    else:
        click.echo(_('Debug is off'))

    printer = ctx.obj['printer']
    config = ctx.obj['config']
    bucket = ctx.obj['bucket']

    engine, config = get_engine(engine, config)

    if ctx.obj['DEBUG']:
        click.echo(_("Engine: %s" % engine))
    engine = engines[engine](config=config)

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(engine.check_processor_statuses())
    printer.print_status_output(result)


@cli.command()
@click.argument('filename') # 'report to read'
@click.pass_context
def render(ctx, filename):
    printer = ctx.obj['printer']
    config = ctx.obj['config']

    with open(filename, 'r') as report_file:
        result = json.load(report_file)

    printer.build_report(result)

    printer.print_output()

@cli.command()
@click.argument('filename') # 'data file to process'
@click.argument('workflow') # 'Python workflow module'
@click.option('-e', '--engine', required=True)
@click.option('-C', '--context', default=None)
@click.option('-a', '--artifact', default=None)
@click.option('-p', '--package', default=None)
@click.option('-c', '--configuration', default=None)
@click.pass_context
def process(ctx, filename, workflow, engine, context, package, configuration, artifact):
    printer = ctx.obj['printer']
    config = ctx.obj['config']
    bucket = ctx.obj['bucket']

    engine, config = get_engine(engine, config)

    if ctx.obj['DEBUG']:
        click.echo(_("Engine: %s" % engine))
    engine = engines[engine](config=config)

    if context is None:
        context = {}
    else:
        with open(context, 'r') as context_file:
            context = json.load(context_file)

    context_args = {}

    if package:
        if package != '.':
            context = context[package]
        context_args['context_package'] = context

    if configuration:
        context_args['configuration'] = json.loads(configuration)

    if context_args:
        context = DoorstepContext(**context_args)
    else:
        context = DoorstepContext.from_dict(context)

    if artifact:
        context.settings['artifact'] = [artifact]

    loop = asyncio.get_event_loop()

    result = loop.run_until_complete(engine.run(filename, workflow, context, bucket=bucket))

    printer.build_report(result)

    printer.print_output()

@cli.command()
@click.option('--engine', required=True)
@click.option('--protocol', type=click.Choice(['http', 'wamp']), required=True)
@click.option('--router', default='#localhost:8080')
@click.pass_context
def serve(ctx, engine, protocol, router):
    printer = ctx.obj['printer']
    config = ctx.obj['config']

    engine, config = get_engine(engine, config)
    click.echo(_("Engine: %s" % engine))
    engine = engines[engine](config=config)

    if protocol == 'http':
        from ltldoorstep.flask_server import launch_flask
        launch_flask(engine)
    elif protocol == 'wamp':
        from ltldoorstep.wamp_server import launch_wamp
        launch_wamp(engine, router, config, debug=ctx.obj['DEBUG'])
    else:
        raise RuntimeError(_("Unknown protocol"))
