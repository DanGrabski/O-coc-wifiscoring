from flask import Blueprint, request, abort, render_template
from datetime import datetime
from os import remove
import time

from .models import *

import ETL as ETL


API = Blueprint("resultsAPI", __name__)

@API.route('/event/<event>/results', methods=['GET', 'POST'])
def results(event):
    if request.method == 'GET':
        #try:
        q = Result.query.filter_by(event=event).all()
        return render_template('basiclist.html', items=q)
        #except:
        #abort(404)

    elif request.method == 'POST':
        timeStart_postResults = time.time()
        try:
            request.files[request.files.keys()[0]].save('latestResultsXML.xml')
        except:
            return 'Please upload an IOF XML ResultsList', 400

        try:
            timeStart_getRunners = time.time()
            results, timestamp = ETL.getRunners('latestResultsXML.xml')
            timeEnd_getRunners = time.time()
        except:
            remove('latestResultsXML.xml')
            return 'GetRunners failed. :(', 500

        newVersion = Version(event, timestamp)
        db.session.add(newVersion)
        db.session.commit()
        version = Version.query.filter_by(event=event).order_by(Version.id.desc()).first()
        v = version.id

        try:
            timeStart_buildDB = time.time()
            for r in results:
                result_dict = { 'sicard': int(r['estick'] if r['estick']>0 else -1),
                                'name': str(r['name']),
                                'bib': int(r['bib'] if r['bib']>0 else -1),
                                'class_code': str(r['class_code']),
                                'club_code': str(r['club']),
                                'time': int(r['time'] if r['time']>0 else -1),
                                'status': str(r['status'])
                              }
                new_result = Result(event, v, result_dict)
                db.session.add(new_result)
            db.session.commit()
            timeEnd_buildDB = time.time()
        except:
            remove('latestResultsXML.xml')
            return 'Problem building up the db refresh', 500

        try:
            timeStart_assignPos = time.time()
            _assignPositions(event, v)
            timeEnd_assignPos = time.time()
            timeStart_assignScore = time.time()
            _assignScores(event, v)
            timeEnd_assignScore = time.time()
        except:
            remove('latestResultsXML.xml')
            return 'Problem assigning individual positions and scores', 500

        try:
            timeStart_teamScore = time.time()
            _assignTeamScores(event, v)
            timeEnd_teamScore = time.time()
            timeStart_teamPos = time.time()
            _assignTeamPositions(event, v)
            timeEnd_teamPos = time.time()
        except:
            remove('latestResultsXML.xml')
            return 'Problem assigning team scores and positions', 500

        # Removing these blocks as they're from NOCI and don't yet work with versioning.
        # This does also cover ULT and WIOL season scoring, but that functionality is
        # being factored OUT of this utility. Driving towards only handling single events.

        # try:
        #     _assignMultiScores(event)
        #     _assignMultiPositions(event)
        # except:
        #     return 'Problem assigning multi-day scores and positions', 500

        # try:
        #     _assignChampPositions()
        # except:
        #     return 'Problem assigning NOCI overall champ postitions', 500


        version.ready = True
        db.session.add(version)
        db.session.commit()

        # TODO: think about deleting old versions from the db
        remove('latestResultsXML.xml')

        timeEnd_postResults = time.time()

        print('{:.4f}s for getRunners'.format(timeEnd_getRunners - timeStart_getRunners))
        print('{:.4f}s for buildDB'.format(timeEnd_buildDB - timeStart_buildDB))
        print('{:.4f}s for assignPos'.format(timeEnd_assignPos - timeStart_assignPos))
        print('{:.4f}s for assignScore'.format(timeEnd_assignScore - timeStart_assignScore))
        print('{:.4f}s for teamScore'.format(timeEnd_teamScore - timeStart_teamScore))
        print('{:.4f}s for teamPos'.format(timeEnd_teamPos - timeStart_teamPos))
        print('{:.4f}s to complete postResults'.format(timeEnd_postResults - timeStart_postResults))

        return 'New Results: {}'.format(version.id), 200

def _assignPositions(event, v):
    event_classes = EventClass.query.filter_by(event=event).filter_by(is_team_class=False).all()
    for c in event_classes:
        class_results = Result.query.filter_by(version=v).filter_by(class_code=c.class_code).filter_by(status="OK").order_by(Result.time).all()
        if len(class_results) == 0: 
            # print 'No results for {}'.format(c.class_name)
            continue
        nextposition = 1
        for i in range(len(class_results)):
            if i == 0:
                class_results[i].position = nextposition
            elif class_results[i].time == class_results[i-1].time:
                class_results[i].position = class_results[i-1].position
            else:
                class_results[i].position = nextposition
            nextposition += 1
        db.session.add_all(class_results)
    db.session.commit()
    return

def _assignScores(event, v):
    event_classes = EventClass.query.filter_by(event=event).filter_by(is_team_class=False).all()
    for c in event_classes:
        if not Result.query.filter_by(version=v).filter_by(class_code=c.class_code).all():
            continue
        if c.score_method == '':
            continue
            
        elif c.score_method == 'WIOL-indv':
            class_results = Result.query.filter_by(version=v).filter_by(class_code=c.class_code).all()
            for r in class_results:
                if r.position < 0:
                    r.score = 0
                elif r.position == 0:
                    raise ValueError
                elif r.position == 1: r.score = 100
                elif r.position == 2: r.score = 95
                elif r.position == 3: r.score = 92
                else:
                    r.score = 100 - 6 - int(r.position)
            db.session.add_all(class_results)

        elif c.score_method == 'NOCI-indv':
            class_results = Result.query.filter_by(version=v).filter_by(class_code=c.class_code).all()
            awt = sum([r.time for r in class_results if (r.position > 0 and r.position <=3)]) / 3.0

            if c.class_code == 'N2M':
                paired_class_code = 'N3F'
            elif c.class_code == 'N3F':
                paired_class_code = 'N2M'
            elif c.class_code == 'N4F':
                paired_class_code = 'N5M'
            elif c.class_code == 'N5M':
                paired_class_code = 'N4F'
            elif c.class_code == 'N1F':
                paired_class_code = 'N1M'
            elif c.class_code == 'N1M':
                paired_class_code = 'N1F'
            else:
                paired_class_code = 'none'

            try:
                paired_results = Result.query.filter_by(version=v).filter_by(class_code=paired_class_code).all()
                paired_awt = sum([r.time for r in paired_results if (r.position > 0 and r.position <=3)]) / 3.0
                better_awt = awt if awt < paired_awt else paired_awt
            except:
                better_awt = 60 * 3 * 3600

            for r in class_results:
                if r.status in ['OK']:
                    r.score = 60 * r.time / awt
                else:
                    r.score = (60 * (3*3600) / better_awt) + 10
            db.session.add_all(class_results)

        elif c.score_method == 'ULT-indv':
            class_results = Result.query.filter_by(version=v).filter_by(class_code=c.class_code).filter(Result.position > 0).all()
            winner = Result.query.filter_by(version=v).filter_by(class_code=c.class_code).filter_by(position=1).one()
            benchmark = float(winner.time)
            for r in class_results:
                if r.time:
                    r.score = round( (benchmark / r.time) * 1000 )
                else:
                    r.score = 0
            db.session.add_all(class_results)

    db.session.commit()
    return

def _assignTeamScores(event, v):
    event_team_classes = EventClass.query.filter_by(event=event).filter_by(is_team_class=True).all()
    for c in event_team_classes:
        if c.score_method == '':
            continue

        elif c.score_method == 'WIOL-team':
            indv_results = []
            for indv_class in c.team_classes.split('-'):
                indv_class = indv_class.strip()
                indv_results += Result.query.filter_by(version=v).filter_by(class_code=indv_class).all()
            teams = set([r.club_code for r in indv_results])
            for team in teams:
                score = 0
                contributors = 0
                members = [r for r in indv_results if ((r.club_code == team) and (r.score > 0))]
                members.sort(key=lambda x: -x.score)
                while ((len(members) > 0) and (contributors < 3)):
                    scorer = members.pop(0)
                    score += scorer.score
                    scorer.is_team_scorer = True
                    contributors += 1
                    db.session.add(scorer)
                if members:
                    for nonscorer in members:
                        nonscorer.is_team_scorer = False
                    db.session.add_all(members)
                team = TeamResult(event, v, c.class_code, team, score, True)
                db.session.add(team)

        elif c.score_method == 'NOCI-team':
            indv_results = []
            for indv_class in c.team_classes.split('-'):
                indv_class = indv_class.strip()
                indv_results += Result.query.filter_by(version=v).filter_by(class_code=indv_class).all()
            teams = set([r.club_code for r in indv_results])
            for team in teams:
                score = 0
                contributors = 0
                members = [r for r in indv_results if (r.club_code == team)]
                members.sort(key=lambda x: x.score)
                while ((len(members) > 0) and (contributors < 3)):
                    scorer = members.pop(0)
                    score += scorer.score
                    scorer.is_team_scorer = True
                    contributors += 1
                    db.session.add(scorer)
                if members:
                    for nonscorer in members:
                        nonscorer.isTeamScorer = False
                    db.session.add_all(members)
                valid = True if contributors == 3 else False
                team = TeamResult(event, v, c.class_code, team, score, valid)
                db.session.add(team)

    db.session.commit()
    return

def _assignTeamPositions(event, v):
    event_team_classes = EventClass.query.filter_by(event=event).filter_by(is_team_class=True).all()
    for c in event_team_classes:
        if c.score_method == '':
            continue

        elif c.score_method == 'WIOL-team':
            team_results = TeamResult.query.filter_by(version=v).filter_by(class_code=c.class_code).all()
            team_results.sort(key=lambda x: -x.score)
            nextposition = 1
            for i in range(len(team_results)):
                if i == 0:
                    team_results[i].position = nextposition
                elif team_results[i].score < team_results[i-1].score:
                    team_results[i].position = nextposition
                else:
                    a_club = team_results[i-1].club_code
                    b_club = team_results[i].club_code
                    a_scorers = []
                    b_scorers = []
                    for indv_class in c.team_classes.split('-'):
                        indv_class = indv_class.strip()
                        a_scorers += Result.query.filter_by(event=event, version=v, class_code=indv_class, club_code=a_club, is_team_scorer=True).all()
                        b_scorers += Result.query.filter_by(event=event, version=v, class_code=indv_class, club_code=b_club, is_team_scorer=True).all()
                    a_scorers.sort(key=lambda x: -x.score)
                    b_scorers.sort(key=lambda x: -x.score)
                    while a_scorers and b_scorers:
                        tiebreakerA = a_scorers.pop(0).score
                        tiebreakerB = b_scorers.pop(0).score
                        if tiebreakerA > tiebreakerB:
                            # print('A wins, assign next position to B\n')
                            team_results[i].position = nextposition
                            break
                        elif tiebreakerB > tiebreakerA:
                            # print('B wins, swapping positions\n')
                            team_results[i].position = team_results[i-1].position
                            team_results[i-1].position = nextposition
                            break
                        else:
                            continue
                    if team_results[i].position == None:
                        if a_scorers:
                            # print('A wins, assign next position to B\n')
                            team_results[i].posoition = nextposition
                            break
                        elif b_scorers:
                            # print('B wins, swapping positions\n')
                            team_results[i].position = team_results[i-1].position
                            team_results[i-1].position = nextposition
                            break
                        else:
                            # print('Actually a Tie!\n')
                            team_results[i].position = team_results[i-1].position
                nextposition += 1
            db.session.add_all(team_results)

        elif c.score_method == 'NOCI-team':
            team_results = TeamResult.query.filter_by(version=v, class_code=c.class_code, is_valid=True).all()
            team_results.sort(key=lambda x: x.score)
            nextposition = 1
            for i in range(len(team_results)):
                if i == 0:
                    team_results[i].position = nextposition
                elif team_results[i].score == team_results[i-1].score:
                    team_results[i].position = team_results[i-1].position
                else:
                    team_results[i].position = nextposition
                nextposition += 1
            db.session.add_all(team_results)

    db.session.commit()
    return

# def _assignMultiScores(event):
#     #TODO: _assignMultiScores() uses ALL events in the database
#     #      which is no longer correct with the addion of versions.
#     #      this needs to be refactored.
#     multi_classes = EventClass.query.filter_by(is_multi_scored=True).filter_by(event=event).all() #filter by event to only get ONE hit for each class.
#     for c in multi_classes:
#         # Delete existing MultiResults
#         if c.is_team_class:
#             MultiResultTeam.query.filter_by(class_code=c.class_code).delete()
#         else:
#             MultiResultIndv.query.filter_by(class_code=c.class_code).delete()

#         if c.multi_score_method == 'time-total':
#             indv_results = Result.query.filter_by(class_code=c.class_code).order_by(Result.bib).all()
#             if len(indv_results) == 0:
#                 continue
#             individuals = _matchMultiResults(indv_results, [], [], lambda x,y: True if x.bib == y.bib else False)
#             num_needed_scores = max([len(x) for x in individuals])
#             for indv in individuals:
#                 score = 0
#                 valid = True
#                 for i in range(len(indv)):
#                     if i == 0:
#                         ids = str(indv[i].id)
#                     else:
#                         ids += '-{}'.format(indv[i].id)                                                
#                     if indv[i].status == 'OK':
#                         score += indv[i].time
#                     else:
#                         valid = False
#                 valid = True if (len(indv) == num_needed_scores) and valid else False
#                 new_multi_result = MultiResultIndv(c.class_code, score, ids, valid)
#                 db.session.add(new_multi_result)
#             db.session.commit()

#         elif c.multi_score_method == 'NOCI-multi':
#             team_results = TeamResult.query.filter_by(class_code=c.class_code, is_valid=True).order_by(TeamResult.club_code).all()
#             if len(team_results) == 0:
#                 continue
#             teams = _matchMultiResults(team_results, [], [], lambda x,y: True if x.club_code == y.club_code else False)
#             num_needed_scores = max([len(x) for x in teams])
#             for team in teams:
#                 for i in range(len(team)):
#                     if i == 0:
#                         club = team[i].club_code
#                         score = team[i].score
#                         ids = str(team[i].id)
#                     else:
#                         score += team[i].score
#                         ids += '-{}'.format(team[i].id)
#                 valid = True if len(team) == num_needed_scores else False
#                 new_multi_team = MultiResultTeam(c.class_code, club, score, ids, valid)
#                 db.session.add(new_multi_team)
#             db.session.commit()            

#         elif c.multi_score_method == 'ULT-season':
#             # TODO: might need better sort by name algorithm here.
#             indv_results = Result.query.filter_by(class_code=c.class_code).order_by(Result.name).all()
#             if len(indv_results) == 0:
#                 continue
#             individuals = _matchMultiResults(indv_results, [], [], lambda x,y: True if x.name == y.name else False)
#             scores_to_count = 6
#             for indv in individuals:
#                 for x in indv:
#                     print x, x.score
#                 indv.sort(key=lambda x: -x.score if x.score else 0)
#                 score = 0
#                 ids = ''
#                 for i in range(len(indv)):
#                     if i < scores_to_count:
#                         score += indv[i].score if indv[i].score else 0
#                     ids += '-{}'.format(indv[i].id)
#                 new_multi_result = MultiResultIndv(c.class_code, score, ids.lstrip('-'), True)
#                 db.session.add(new_multi_result)
#             db.session.commit()

#         else:
#             pass
#     return

# def _matchMultiResults(input, same, output, matchf):
#     if len(input) == 0:
#         output.append(same)
#         return output
#     else:
#         i = input.pop()
#         if (len(same) == 0) or matchf(i, same[0]):
#             same.append(i)
#             return _matchMultiResults(input, same, output, matchf)
#         else:
#             output.append(same)
#             same = [i]
#             return _matchMultiResults(input, same, output, matchf)

# def _assignMultiPositions(event):
#     multi_classes = EventClass.query.filter_by(is_multi_scored=True).filter_by(event=event).all()
#     if len(multi_classes) == 0:
#         return
#     for c in multi_classes:
#         if c.multi_score_method == 'time-total':
#             multi_results = MultiResultIndv.query.filter_by(class_code=c.class_code, is_valid=True).all()
#             multi_results.sort(key=lambda x: x.score) # Low is better
#             nextposition = 1
#             for i in range(len(multi_results)):
#                 # if not multi_results[i].is_valid:
#                     # multi_results[i].position = -1
#                     # continue
#                 if i == 0:
#                     multi_results[i].position = nextposition
#                 elif multi_results[i].score == multi_results[i-1].score:
#                     multi_results[i].position = multi_results[i-1].position
#                 else:
#                     multi_results[i].position = nextposition
#                 nextposition += 1
#             db.session.add_all(multi_results)
#             db.session.commit()

#         elif c.multi_score_method == 'NOCI-multi':
#             multi_results = MultiResultTeam.query.filter_by(class_code=c.class_code, is_valid=True).all()
#             multi_results.sort(key=lambda x: x.score) # Low is better
#             nextposition = 1
#             for i in range(len(multi_results)):
#                 if i == 0:
#                     multi_results[i].position = nextposition
#                 elif multi_results[i].score == multi_results[i-1].score:
#                     multi_results[i].position = multi_results[i-1].position
#                 else:
#                     multi_results[i].position = nextposition
#                 nextposition += 1

#             for twoday_team in multi_results:
#                 if c.class_code in ['NTV', 'NTJV']:
#                     if c.class_code == 'NTV':
#                         champscore = 300 - 30*(twoday_team.position - 1)
#                     elif c.class_code == 'NTJV':
#                         champscore = 200 - 20*(twoday_team.position - 1)
#                     twoday_team.champ_score = champscore if champscore > 0 else 0
#                 else:
#                     twoday_team.champ_score = None
#             db.session.add_all(multi_results)
#             db.session.commit()


#         elif c.multi_score_method == 'WIOL-season':
#             multi_results = MultiResultIndv.query.filter_by(class_code=c.class_code).all()
#             multi_results.sort(key=lambda x: -x.score) # High is better, sort high to the front with -x.
#             nextposition = 1
#             for i in range(len(multi_results)):
#                 if i == 0:
#                     multi_results[i].position = nextposition
#                 elif multi_results[i].score == multi_results[i-1].score:
#                     multi_results[i].position = multi_results[i-1].position
#                 else:
#                     multi_results[i].position = nextposition
#                 nextposition += 1
#                 # TODO: Implement WIOL season tie-breaking
#             db.session.add_all(multi_results)
#             db.session.commit()

#         elif c.multi_score_method == 'ULT-season':
#             multi_results = MultiResultIndv.query.filter_by(class_code=c.class_code).all()
#             multi_results.sort(key=lambda x: -x.score) # High is better, sort high to the front with -x.
#             nextposition = 1
#             for i in range(len(multi_results)):
#                 if i == 0:
#                     multi_results[i].position = nextposition
#                 elif multi_results[i].score == multi_results[i-1].score:
#                     multi_results[i].position = multi_results[i-1].position
#                 else:
#                     multi_results[i].position = nextposition
#                 nextposition += 1
#                 # TODO: Implement Ultimate season tie-breaking
#             db.session.add_all(multi_results)
#             db.session.commit()

#         else:
#             pass
#     return


# def _assignChampPositions():
#     champ_class = EventClass.query.filter_by(score_method='NOCIuber').first()
#     if champ_class is None:
#         return
#     multi_teams = []
#     for team_class in champ_class.team_classes.split('-'):
#         team_class = team_class.strip()
#         multi_teams += MultiResultTeam.query.filter_by(class_code=team_class, is_valid=True).all()
#     multi_teams.sort(key=lambda x: x.club_code)
#     champ_teams = _matchMultiResults(multi_teams, [], [], lambda x,y: True if x.club_code == y.club_code else False)
#     for club in champ_teams:
#         if len(club) < 1:
#             continue
#         v = False
#         jv = False
#         score = 0
#         ids = ''
#         club_code = club[0].club_code
#         for i in range(len(club)):
#             v = True if v or club[i].class_code == 'NTV' else False
#             jv = True if jv or club[i].class_code == 'NTJV' else False
            
#             if i == 0:
#                 ids += str(club[i].id)
#             else:
#                 ids += '-{}'.format(club[i].id)
#             if club[i].class_code in ['NTV', 'NTJV']:
#                 score += club[i].champ_score
#         valid = True if v and jv else False
#         new_champ_team = MultiResultTeam(champ_class.class_code, club_code, score, ids, valid)
#         db.session.add(new_champ_team)
#     db.session.commit()
    
#     champ_teams = MultiResultTeam.query.filter_by(class_code=champ_class.class_code, is_valid=True).all()
#     champ_teams.sort(key=lambda x: -x.score) #higher better
#     nextposition = 1
#     for i in range(len(champ_teams)):
#         if i == 0:
#             champ_teams[i].position = nextposition
#         elif champ_teams[i].score == champ_teams[i-1].score:
#             champ_teams[i].position = champ_teams[i-1].position
#         else:
#             champ_teams[i].position = nextposition
#         nextposition += 1
    
#     db.session.add_all(champ_teams)
#     db.session.commit()
#     return

@API.route('/teams', methods=['GET'])
def teams():
    q = TeamResult.query.all()
    return render_template('basiclist.html', items = q)
        

@API.route('/clubs', methods=['GET', 'PUT', 'DELETE'])
def clubs():
    """ Mapping of Club/Team code to full name
    
    GET returns a view of all clubs
    PUT accepts a list of clubs and will update data
    DELETE will clear the entire collection
    """
    
    if request.method == 'GET':
        q = Club.query.all()
        return render_template('basiclist.html', items=q)

    elif request.method == 'PUT':
        f = request.files[request.files.keys()[0]]
        clubs = ETL.clubcodejson(f)
        for club in clubs:
            # abbr = club['abbr']
            abbr = club['code']
            full = club['name']
            q = Club.query.filter_by(club_code=abbr).all()
            
            if len(q) > 2:
                return 'Internal Error: Multiple clubs found for ' + abbr, 500
                
            if not q:
                new_club = Club(abbr, full)
                db.session.add(new_club)
                
            elif q:
                existing_club = q[0]
                if existing_club.club_name != full:
                    existing_club.club_name = full
                    db.session.add(existing_club)
                    
        db.session.commit()
        return 'Clubs table updated', 200

    elif request.method == 'DELETE':
        pass
        

@API.route('/event/<event>/classes', methods=['GET', 'PUT', 'DELETE'])
def cclasses(event):
    """ Mapping of class code to full name
    
    GET returns a view of all classes
    PUT accepts a list of classes and will update data
    DELETE will clear the entire collection
    """
    
    if request.method == 'GET':
        q = EventClass.query.filter_by(event=event).all()
        return render_template('basiclist.html', items=q)

    elif request.method == 'PUT':
        # TODO: make this a PUT rather than a wipe and reload.
        EventClass.query.filter_by(event=event).delete()

        f = request.files[request.files.keys()[0]].save('~latestclassinfo.csv')
        with open('~latestclassinfo.csv') as infile:
            # eventClasses = ETL.classCSV('~latestclassinfo.csv')
            eventClasses = ETL.classCSV(infile)
            for c in eventClasses:
                new_class = EventClass(event, c)
                db.session.add(new_class)
            db.session.commit()
        remove(f)
        return 'Refreshed EventClass table', 200

    elif request.method == 'DELETE':
        pass

@API.route('/events', methods=['GET', 'PUT', 'DELETE'])
def events():
    """ Mapping of class code to full name
    
    GET returns a view of all classes
    PUT accepts a list of classes and will update data
    DELETE will clear the entire collection
    """
    
    if request.method == 'GET':
        q = Event.query.all()
        return render_template('basiclist.html', items=q)

    elif request.method == 'PUT':
        f = request.files[request.files.keys()[0]].save('~latesteventinfo.tsv')
        events = ETL.eventsTSV('~latesteventinfo.tsv')

        # TODO: make this a PUT rather than a wipe and reload.
        Event.query.delete()

        for e in events:
            new_event = Event(e['event_code'], e['event_name'], e['date'], e['venue'], e['description'])
            db.session.add(new_event)
        db.session.commit()
        remove(f)
        return 'Refreshed Event table', 200

    elif request.method == 'DELETE':
        pass
        
@API.route('/event/<event>/entries', methods=['GET','PUT'])
def entries(event):
    """ Name to class and SIcard mapping
    
    GET returns evertyhing
    PUT accepts an iof3 XML entries list and updates data
    DELETE clears the collection
    """
    if request.method == 'GET':
        q = Entry.query.filter_by(event=event).all()
        return render_template('basiclist.html', items=q)
        
    if request.method == 'PUT':
        request.files[request.files.keys()[0]].save('entries.xml')
        entries = ETL.entriesXML3('entries.xml')
        for e in entries:
            new_entry = Entry(event, e['name'], e['cclass'], e['club'], e['sicard'])
            db.session.add(new_entry)
        db.session.commit()
        return 'Updated Entries', 200