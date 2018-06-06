$(document).on("click", "#overview", function () {
    $("#main-menu a.nav-link").removeClass("active");
    $("#overview").addClass("active");
    $("#user-list").addClass("hidden");
    $("#map").css({ top: '70px' });

    map.setLayoutProperty('all-visits-heat', 'visibility', 'visible');
    map.setLayoutProperty('all-visits-point', 'visibility', 'visible');

    if (pointsLayer) {
        map.setLayoutProperty('day-points', 'visibility', 'none');
    }
});

$(document).on("click", "#users", function () {
    $("#main-menu a.nav-link").removeClass("active");
    $("#users").addClass("active");
    $("#user-list").removeClass("hidden");
    $("#map").css({ top: '70px' });
});

$(document).on("click", ".list-group-item", function () {
    $('#user-days ul').empty();
    $("#map").css({ top: '150px' });

    var userId = $(this).data("id");

    // populate the user-days
    var items = [];
    $.each(users[userId]['days'], function(i, day) {
      items.push('<li class="nav-item"><a class="nav-link" data-toggle="pill" data-user="'+userId+'" data-day="'+day+'" href="#'+day+'">'+day+'</a></li>');
    });  // close each()

    $('#user-days ul').append( items.join('') );
});

$(document).on("click", "#user-days .nav-link", function () {
    var userId = $(this).data("user");
    var day = $(this).data("day");

    var params = {
        day: day,
        userid: userId,
        type: "geojson"
    };
    $.getJSON('/rawtrace', params, function(data) {
        map.setLayoutProperty('all-visits-heat', 'visibility', 'none');
        map.setLayoutProperty('all-visits-point', 'visibility', 'none');

        if (pointsLayer) {
            map.setLayoutProperty('day-points', 'visibility', 'visible');
            map.getSource('day-points').setData(data);
        } else {
            map.addSource('day-points', {
                "type": "geojson",
                "data": data
            });

            map.addLayer({
                "id": "day-points",
                "source": "day-points",
                "type": "circle",
                "paint": {
                    "circle-radius": 5,
                    "circle-color": "#007cbf",
                    "circle-opacity": 0.5
                }
            });
            pointsLayer = true;
        }

        console.log(data)
    });
});

map.on('load', init);