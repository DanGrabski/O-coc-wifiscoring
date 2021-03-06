from flask import Blueprint, request, abort, render_template
from datetime import time

from .models import db, RemotePunch, Result, Entry

from coc_wifiscoring import socketio

telemetry = Blueprint("telemetry", __name__)

@telemetry.route('/<int:control>', methods=['GET'])
def get_punches(control):
    try:
        punches = RemotePunch.query.filter_by(station=control).order_by(RemotePunch.time).all()
        punches.reverse()
        silookup = {}
        entries = Entry.query.all()
        for e in entries:
            silookup[e.sicard] = e.name
        return render_template('telemetry.html', box=control, punches=punches, names=silookup)
    except:
        abort(404)


@telemetry.route('/<int:control>', methods=['POST'])
def record_punch(control):
    try:
        body = request.get_json(force=True) #read json without json mimetype in header
        h,m,s = body['time'].split(':',3)
        punch = RemotePunch(body['station'], body['sicard'], time(int(h),int(m),int(s)))
        db.session.add(punch)
        db.session.commit()
        entry = Entry.query.filter_by(sicard=body['sicard']).first()
        name = entry.name if entry else ''
        socketio.emit('new punch', {'station': body['station'], 'sicard':body['sicard'], 'time':body['time'], 'name':name})
        return str(punch), 200
    except:
        abort(500)


@telemetry.route('/outcount/<int:startcode>')
def out_count(startcode):
    starters = RemotePunch.query.filter_by(station=startcode).all()
    downloadcards = Result.query.from_self(Result.sicard).all()
    downloadcards = [a[0] for a in downloadcards]
    out = []
    for s in starters:
        if s.sicard in downloadcards:
            continue
        else:
            out.append(s)
    return render_template('basiclist.html', items=out)


@telemetry.route('/')
def hello():
    return 'Hello telemetry world!'
