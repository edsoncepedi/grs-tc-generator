from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from sqlalchemy import and_, desc, func
from sqlalchemy.exc import IntegrityError
import json
from app.database.factories.database_manager import DatabaseManager
from app.models.telecommand import Telecommand
from app.models.satellite import Satellite
from app.models.scheduled_pass import ScheduledPass
from app.models.operator import Operator
from app.services import celestrak

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def index():
    """Render the main dashboard with telecommands grouped by status."""
    session = DatabaseManager.get_session()
    try:
        pending_filter = Telecommand.status.in_(['pending', 'queued'])
        sent_filter = Telecommand.status == 'sent'
        # The card says "24h", so the query has to mean it.
        last_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        history_filter = and_(
            Telecommand.status.in_(['confirmed', 'failed']),
            Telecommand.created_at >= last_24h,
        )

        # The lists are capped at 10 for a readable page, but the cards must
        # count every row: taking len() of a capped list makes the counter
        # silently stop at 10 once the queue grows past it.
        counts = {
            'pending': session.query(func.count(Telecommand.id)).filter(pending_filter).scalar(),
            'sent': session.query(func.count(Telecommand.id)).filter(sent_filter).scalar(),
            'history': session.query(func.count(Telecommand.id)).filter(history_filter).scalar(),
        }

        pending_tcs = session.query(Telecommand)\
            .filter(pending_filter)\
            .order_by(desc(Telecommand.created_at))\
            .limit(10).all()

        sent_tcs = session.query(Telecommand)\
            .filter(sent_filter)\
            .order_by(desc(Telecommand.sent_at))\
            .limit(10).all()

        history_tcs = session.query(Telecommand)\
            .filter(history_filter)\
            .order_by(desc(Telecommand.created_at))\
            .limit(10).all()

        # Fetch all satellites (not just active) for the sidebar list
        satellites = session.query(Satellite).order_by(Satellite.name).all()

        # Fetch operators (In a real app, this would be the logged-in user)
        operators = session.query(Operator).filter_by(status='active').all()

        return render_template(
            'index.html',
            counts=counts,
            pending_tcs=pending_tcs,
            sent_tcs=sent_tcs,
            history_tcs=history_tcs,
            satellites=satellites,
            operators=operators
        )
    finally:
        session.close()

# --- Telecommand Routes ---

@web_bp.route('/telecommand/create', methods=['POST'])
def create_telecommand():
    """Handle telecommand creation form submission."""
    session = DatabaseManager.get_session()
    try:
        data = request.form
        
        # Parse parameters JSON if provided
        params = {}
        if data.get('parameters'):
            try:
                params = json.loads(data['parameters'])
            except json.JSONDecodeError:
                flash('Invalid JSON in parameters field', 'warning')
                return redirect(url_for('web.index'))

        new_tc = Telecommand(
            satellite_id=int(data['satellite_id']),
            operator_id=int(data['operator_id']),
            command_type=data['command_type'],
            priority=int(data['priority']),
            status='pending',
            parameters=params
        )
        
        session.add(new_tc)
        session.commit()
        flash('Telecommand created successfully!', 'success')
        
    except Exception as e:
        session.rollback()
        flash(f'Error creating telecommand: {str(e)}', 'danger')
    finally:
        session.close()
        
    return redirect(url_for('web.index'))

@web_bp.route('/telecommand/update/<int:tc_id>', methods=['POST'])
def update_telecommand(tc_id):
    """Handle telecommand updates via AJAX."""
    session = DatabaseManager.get_session()
    try:
        tc = session.get(Telecommand, tc_id)
        if not tc:
            return jsonify({'success': False, 'error': 'Telecommand not found'}), 404
            
        # Get JSON data from request body
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # Update fields if provided
        if 'parameters' in data:
            tc.parameters = data['parameters']
        
        if 'satellite_id' in data:
            tc.satellite_id = int(data['satellite_id'])
            
        if 'command_type' in data:
            tc.command_type = data['command_type']
            
        if 'priority' in data:
            tc.priority = int(data['priority'])
            
        if 'status' in data:
            if hasattr(tc, 'update_status'):
                tc.update_status(data['status'])
            else:
                tc.status = data['status']
            
        session.commit()
        return jsonify({'success': True, 'message': 'Telecommand updated successfully'})
        
    except Exception as e:
        session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

@web_bp.route('/telecommand/delete/<int:tc_id>', methods=['POST'])
def delete_telecommand(tc_id):
    """Handle telecommand deletion."""
    session = DatabaseManager.get_session()
    try:
        tc = session.get(Telecommand, tc_id)
        if tc:
            session.delete(tc)
            session.commit()
            flash(f'Telecommand {tc_id} deleted.', 'success')
        else:
            flash('Telecommand not found.', 'warning')
    except Exception as e:
        session.rollback()
        flash(f'Error deleting: {str(e)}', 'danger')
    finally:
        session.close()
        
    return redirect(url_for('web.index'))

# --- Satellite Routes ---

def _clean_orbital_field(value):
    """Empty form fields mean "not set", which in the database is NULL.

    Storing '' instead would make norad_id fail its integer cast and would make
    an empty TLE look like a manual TLE that the scheduler must prefer.
    """
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _apply_orbital_data(satellite, data):
    """Set norad_id / TLE lines from request data, validating against CelesTrak.

    Returns a warning string when the ID could not be confirmed but was still
    accepted, or None when there is nothing to report.

    A NORAD ID that points at the wrong object never fails visibly — the station
    just tracks something else — so it is checked against the same catalogue the
    trajectory calculation uses. If CelesTrak itself is unreachable the value is
    accepted with a warning: refusing to register satellites because an external
    site is down would be worse than the risk of a typo.
    """
    warning = None

    if 'norad_id' in data:
        raw = _clean_orbital_field(data.get('norad_id'))
        if raw is None:
            satellite.norad_id = None
        else:
            try:
                norad_id = int(raw)
            except (TypeError, ValueError):
                raise ValueError(f'NORAD ID must be a number, got {raw!r}')

            try:
                entry = celestrak.lookup_by_norad_id(norad_id)
            except celestrak.CelestrakUnavailable as error:
                warning = (
                    f'NORAD {norad_id} saved without confirmation: '
                    f'CelesTrak is unreachable ({error})'
                )
            else:
                if entry is None:
                    raise ValueError(
                        f'NORAD {norad_id} does not exist in the CelesTrak catalogue. '
                        f'Search by name to find the right identifier.'
                    )
            satellite.norad_id = norad_id

    if 'tle_line1' in data:
        satellite.tle_line1 = _clean_orbital_field(data.get('tle_line1'))
    if 'tle_line2' in data:
        satellite.tle_line2 = _clean_orbital_field(data.get('tle_line2'))

    if bool(satellite.tle_line1) != bool(satellite.tle_line2):
        raise ValueError('A manual TLE needs both lines, or neither.')

    return warning


@web_bp.route('/satellites')
def satellites_page():
    """Satellite registry: orbital data, tracking state and upcoming passes."""
    session = DatabaseManager.get_session()
    try:
        satellites = session.query(Satellite).order_by(Satellite.name).all()

        now = datetime.now(timezone.utc)
        next_passes = {}
        for scheduled in (session.query(ScheduledPass)
                          .filter(ScheduledPass.status.in_(['planned', 'active']))
                          .filter(ScheduledPass.los_time >= now)
                          .order_by(ScheduledPass.aos_time).all()):
            next_passes.setdefault(scheduled.satellite_id, scheduled)

        return render_template(
            'satellites.html', satellites=satellites, next_passes=next_passes, now=now
        )
    finally:
        session.close()


@web_bp.route('/satellite/lookup')
def satellite_lookup():
    """Search the CelesTrak catalogue, so an operator never guesses a NORAD ID."""
    query = (request.args.get('q') or '').strip()
    if not query:
        return jsonify({'success': False, 'error': 'Informe um nome ou NORAD ID'}), 400

    try:
        if query.isdigit():
            entry = celestrak.lookup_by_norad_id(int(query))
            results = [entry] if entry else []
        else:
            results = celestrak.search_by_name(query)
    except celestrak.CelestrakUnavailable as error:
        return jsonify({'success': False, 'error': f'CelesTrak indisponível: {error}'}), 503

    return jsonify({'success': True, 'results': results})


@web_bp.route('/satellite/create', methods=['POST'])
def create_satellite():
    """Handle satellite creation via AJAX."""
    session = DatabaseManager.get_session()
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        new_sat = Satellite(
            name=data['name'],
            code=data['code'],
            status=data['status'],
            description=data.get('description', '')
        )
        warning = _apply_orbital_data(new_sat, data)

        session.add(new_sat)
        session.commit()
        return jsonify({
            'success': True, 'message': 'Satellite created successfully', 'warning': warning
        })

    except ValueError as e:
        session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except IntegrityError:
        session.rollback()
        return jsonify({
            'success': False,
            'error': 'Satellite code and NORAD ID must be unique.'
        }), 400
    except Exception as e:
        session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

@web_bp.route('/satellite/update/<int:sat_id>', methods=['POST'])
def update_satellite(sat_id):
    """Handle satellite updates via AJAX."""
    session = DatabaseManager.get_session()
    try:
        sat = session.get(Satellite, sat_id)
        if not sat:
            return jsonify({'success': False, 'error': 'Satellite not found'}), 404

        data = request.get_json()

        if 'name' in data: sat.name = data['name']
        if 'code' in data: sat.code = data['code']
        if 'status' in data: sat.status = data['status']
        if 'description' in data: sat.description = data['description']
        warning = _apply_orbital_data(sat, data)

        session.commit()
        return jsonify({
            'success': True, 'message': 'Satellite updated successfully', 'warning': warning
        })

    except ValueError as e:
        session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except IntegrityError:
        session.rollback()
        return jsonify({
            'success': False,
            'error': 'Satellite code and NORAD ID must be unique.'
        }), 400
    except Exception as e:
        session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

@web_bp.route('/satellite/delete/<int:sat_id>', methods=['POST'])
def delete_satellite(sat_id):
    """Handle satellite deletion."""
    session = DatabaseManager.get_session()
    try:
        sat = session.get(Satellite, sat_id)
        if sat:
            session.delete(sat)
            session.commit()
            flash(f'Satellite {sat.name} deleted.', 'success')
        else:
            flash('Satellite not found.', 'warning')
    except Exception as e:
        session.rollback()
        flash(f'Error deleting satellite: {str(e)}', 'danger')
    finally:
        session.close()

    # Back to wherever the delete was triggered from: the registry page lists
    # satellites, the dashboard has them in the sidebar.
    if request.referrer and url_for('web.satellites_page') in request.referrer:
        return redirect(url_for('web.satellites_page'))
    return redirect(url_for('web.index'))
